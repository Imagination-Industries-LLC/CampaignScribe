"""The real first-run installer: venv, pip upgrade, pip install, verify.

Standard library only. ``Installer.run`` is injectable so the command sequence is
unit-testable without a real multi-GB install.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from bootstrap import core

VERIFY_TIMEOUT = 120


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    cuda_ok: bool
    message: str = ""


def count_lock_lines(lock_file: str | Path) -> int:
    """Requirement lines in a lock: excludes comments, blanks and option lines (--extra-index-url)."""
    count = 0
    for raw in Path(lock_file).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith(("#", "-")):
            count += 1
    return count


def package_name(token: str) -> str:
    """'torch==2.5.1+cu124' -> 'torch'."""
    return re.split(r"[=<>!~;\[ ]", token, maxsplit=1)[0]


class Installer:
    """Callable ``(profile, log_cb, progress_cb) -> InstallResult`` plus cancel/cleanup hooks."""

    def __init__(self, app_home, run=None, base_python=None):
        self.app_home = Path(app_home)
        self._run = run or self._stream_run
        self._base_python = base_python
        self._cancelled = False
        self._proc = None
        self._lock = threading.Lock()

    # --- paths -------------------------------------------------------------

    def base_python(self) -> Path:
        """The interpreter that creates the venv: {app}/python/python.exe when installed.

        In a dev checkout there is no {app}/python, so fall back to python.exe next
        to sys.executable (the dev venv's interpreter) for manual testing.
        """
        if self._base_python:
            return Path(self._base_python)
        bundled = self.app_home / "python" / "python.exe"
        if bundled.exists():
            return bundled
        return Path(sys.executable).parent / "python.exe"

    @staticmethod
    def env_python() -> Path:
        return core.env_dir() / "Scripts" / "python.exe"

    # --- hooks -------------------------------------------------------------

    def cancel(self) -> None:
        """Flag cancellation and kill the running process tree.

        Only the worker deletes files (it runs cleanup itself once the process is
        gone), so cancel never races a step that is still writing.
        """
        self._cancelled = True
        with self._lock:
            proc = self._proc
        if proc is not None:
            _kill_tree(proc)

    def cleanup(self, attempts: int = 1, delay: float = 0.5) -> str | None:
        """Remove a partial environment. State goes first so it can never look complete.

        Returns the leftover env path if files remain after ``attempts`` tries
        (e.g. locked by antivirus), else None.
        """
        _remove_state()
        env = core.env_dir()
        for i in range(max(attempts, 1)):
            shutil.rmtree(env, ignore_errors=True)
            if not env.exists():
                return None
            if i + 1 < attempts:
                time.sleep(delay)
        return str(env)

    # --- default runner ----------------------------------------------------

    def _stream_run(self, cmd, line_cb, timeout=None):
        env = dict(os.environ)
        env.update(PYTHONIOENCODING="utf-8", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
        try:
            proc = subprocess.Popen(  # noqa: S603  # nosec B603 - fixed argv, no shell
                [str(c) for c in cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=core.no_window_flags(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Python runtime not found at {cmd[0]}") from exc
        with self._lock:
            self._proc = proc
        timed_out = threading.Event()

        def on_timeout():
            timed_out.set()
            _kill_tree(proc)

        timer = None
        if timeout:
            timer = threading.Timer(timeout, on_timeout)
            timer.daemon = True
            timer.start()
        if self._cancelled:  # cancel() ran before the process was registered
            _kill_tree(proc)
        lines = []
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                lines.append(line)
                line_cb(line)
            proc.wait()
        finally:
            if timer is not None:
                timer.cancel()
            with self._lock:
                self._proc = None
        if timed_out.is_set():
            line_cb(f"Timed out after {timeout} s")
            return -1, "\n".join(lines)
        return proc.returncode, "\n".join(lines)

    # --- the install -------------------------------------------------------

    def __call__(self, profile, log_cb, progress_cb) -> InstallResult:
        self._cancelled = False
        try:
            return self._install(profile, log_cb, progress_cb)
        except Exception as exc:  # noqa: BLE001 - any failure becomes a failure result
            log_cb(f"Setup error: {exc}")
            if self._cancelled:
                return self._cancelled_result()
            return InstallResult(False, False, str(exc))

    def _cancelled_result(self) -> InstallResult:
        leftover = self.cleanup(attempts=6)
        msg = "Cancelled"
        if leftover:
            msg += f"; could not remove {leftover} (files in use) - delete it manually"
        return InstallResult(False, False, msg)

    def _emit(self, log_cb):
        log_file = core.setup_log_path()
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        def emit(line: str) -> None:
            log_cb(line)
            try:
                with open(log_file, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass

        return emit

    def _step(self, label, cmd, emit, timeout=None, line_cb=None):
        if self._cancelled:
            return None, "Cancelled"
        emit(f"== {label}")
        emit("$ " + " ".join(str(c) for c in cmd))
        rc, out = self._run(cmd, line_cb or emit, timeout)
        if self._cancelled:
            return None, "Cancelled"
        if rc != 0:
            return None, f"{label} failed (exit code {rc})"
        return out, ""

    def _fail(self, err) -> InstallResult:
        if self._cancelled:
            return self._cancelled_result()
        return InstallResult(False, False, err)

    def _install(self, profile, log_cb, progress_cb) -> InstallResult:
        if profile not in core.PROFILES:
            return InstallResult(False, False, f"unknown profile {profile!r}")
        emit = self._emit(log_cb)
        lock_file = core.lock_path(self.app_home, profile)
        total = count_lock_lines(lock_file)
        env_py = self.env_python()

        # Interrupted-run safety (Review Focus 2): state first, then the env, then the venv.
        self.cleanup()

        _, err = self._step(
            "Creating environment",
            [self.base_python(), "-m", "venv", core.env_dir()],
            emit,
        )
        if err:
            return self._fail(err)

        pip_version = core.lock_pip_version(lock_file)
        if pip_version:
            _, err = self._step(
                "Upgrading pip", core.pip_upgrade_command(env_py, pip_version), emit
            )
            if err:
                return self._fail(err)

        counter = core.ProgressCounter(total)

        def pip_line(line: str) -> None:
            emit(line)
            done, tot, name = counter.feed(line)
            progress_cb(done, tot, package_name(name) if name else None)

        _, err = self._step(
            "Installing libraries",
            core.pip_command(env_py, lock_file),
            emit,
            line_cb=pip_line,
        )
        if err:
            return self._fail(err)

        out, err = self._step(
            "Verifying", core.verify_command(env_py), emit, timeout=VERIFY_TIMEOUT
        )
        if err:
            return self._fail(err)
        try:
            _torch, cuda_ok = core.parse_verify(out)
        except ValueError as exc:
            emit(f"Verify output not understood: {exc}")
            return InstallResult(False, False, f"Verifying failed: {exc}")

        if self._cancelled:  # never record success after a cancel
            return self._cancelled_result()
        core.write_state(
            profile,
            core.lock_sha256(lock_file),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        progress_cb(total, total, None)
        return InstallResult(True, cuda_ok, "")


def _kill_tree(proc) -> None:
    """Kill proc and its children. A venv's python.exe on Windows is a redirector
    whose real interpreter is a child, so killing only the parent orphans pip."""
    if sys.platform == "win32":
        try:
            subprocess.run(  # noqa: S603  # nosec B603 B607 - fixed argv, no shell
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
                creationflags=core.no_window_flags(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _remove_state() -> None:
    try:
        core.state_path().unlink()
    except FileNotFoundError:
        pass


def make_installer(app_home) -> Installer:
    return Installer(app_home)
