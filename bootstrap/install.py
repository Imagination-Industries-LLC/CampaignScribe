"""The real first-run installer: venv, pip upgrade, pip install, verify.

Standard library only. ``Installer.run`` is injectable so the command sequence is
unit-testable without a real multi-GB install.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
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
        """Terminate the running pip/venv process; the next step will not start."""
        self._cancelled = True
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def cleanup(self) -> None:
        """Remove a partial environment. State goes first so it can never look complete."""
        _remove_state()
        shutil.rmtree(core.env_dir(), ignore_errors=True)

    # --- default runner ----------------------------------------------------

    def _stream_run(self, cmd, line_cb, timeout=None):
        proc = subprocess.Popen(  # noqa: S603  # nosec B603 - fixed argv, no shell
            [str(c) for c in cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=core.no_window_flags(),
        )
        with self._lock:
            self._proc = proc
        timer = None
        if timeout:
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
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
        return proc.returncode, "\n".join(lines)

    # --- the install -------------------------------------------------------

    def __call__(self, profile, log_cb, progress_cb) -> InstallResult:
        self._cancelled = False
        try:
            return self._install(profile, log_cb, progress_cb)
        except Exception as exc:  # noqa: BLE001 - any failure becomes a failure result
            log_cb(f"Setup error: {exc}")
            return InstallResult(False, False, str(exc))

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
        emit(f"== {label}")
        emit("$ " + " ".join(str(c) for c in cmd))
        rc, out = self._run(cmd, line_cb or emit, timeout)
        if self._cancelled:
            return None, "Cancelled"
        if rc != 0:
            return None, f"{label} failed (exit code {rc})"
        return out, ""

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
            return InstallResult(False, False, err)

        pip_version = core.lock_pip_version(lock_file)
        if pip_version:
            _, err = self._step(
                "Upgrading pip", core.pip_upgrade_command(env_py, pip_version), emit
            )
            if err:
                return InstallResult(False, False, err)

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
            return InstallResult(False, False, err)

        out, err = self._step(
            "Verifying", core.verify_command(env_py), emit, timeout=VERIFY_TIMEOUT
        )
        if err:
            return InstallResult(False, False, err)
        try:
            _torch, cuda_ok = core.parse_verify(out)
        except ValueError as exc:
            emit(f"Verify output not understood: {exc}")
            return InstallResult(False, False, f"Verifying failed: {exc}")

        core.write_state(
            profile,
            core.lock_sha256(lock_file),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        progress_cb(total, total, None)
        return InstallResult(True, cuda_ok, "")


def _remove_state() -> None:
    try:
        core.state_path().unlink()
    except FileNotFoundError:
        pass


def make_installer(app_home) -> Installer:
    return Installer(app_home)
