"""Tk-free Python side of the Discord live recorder.

Drives the Node helper (recorder/recorder.mjs) over its JSON-lines stdio protocol, and handles
the token, invite link, per-user PCM -> WAV conversion and crash-recovery helpers.

The bot token is never printed, logged, written to a file or put on a command line: it travels
only in the child's environment (DISCORD_TOKEN) and is stored only in the keyring.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app import config
from app.core import audio

INVITE_PERMISSIONS = 1051648
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_STDERR_CAP = 200
_STOP_LINE = '{"cmd":"stop"}' + chr(10)

_UNAVAILABLE_MSG = "Reinstall CampaignScribe, or in a development checkout run: python scripts/fetch_node_runtime.py"


class RecorderUnavailable(RuntimeError):
    """The bundled Node runtime / recorder script cannot be found."""


class RecorderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---- paths ------------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _frozen_base() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return None


def node_exe() -> str:
    base = _frozen_base()
    if base is not None:
        return str(base / "node" / "node.exe")
    vendored = _repo_root() / "vendor" / "node" / "node.exe"
    if vendored.exists():
        return str(vendored)
    found = shutil.which("node")
    if found:
        return found
    raise RecorderUnavailable(_UNAVAILABLE_MSG)


def recorder_script() -> str:
    base = _frozen_base()
    if base is not None:
        return str(base / "recorder" / "recorder.mjs")
    return str(_repo_root() / "recorder" / "recorder.mjs")


def recordings_root(cfg: dict | None = None) -> str:
    if cfg is None:
        cfg = config.load_config()
    folder = (cfg.get("recordings_folder") or "").strip()
    if folder:
        return folder
    out = (cfg.get("default_output_folder") or "").strip()
    if out:
        return os.path.join(out, "recordings")
    return str(config.get_app_data_dir() / "recordings")


def new_recording_dir(session_id: int, now: datetime | None = None, cfg: dict | None = None) -> str:
    now = now or datetime.now()
    path = os.path.join(
        recordings_root(cfg), f"session_{session_id}_{now.strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(path, exist_ok=True)
    return path


# ---- token / invite ---------------------------------------------------------------------


def get_token() -> str:
    return config.get_discord_token()


def save_token(token: str) -> None:
    config.save_discord_token(token)


def application_id_from_token(token: str) -> str | None:
    """A bot token's first segment is the base64url of the application (user) id."""
    try:
        seg = (token or "").strip().split(".")[0]
        if not seg:
            return None
        raw = base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))
        text = raw.decode("ascii")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return text if text.isdigit() else None


def invite_url(token: str) -> str | None:
    app_id = application_id_from_token(token)
    if not app_id:
        return None
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={app_id}&scope=bot&permissions={INVITE_PERMISSIONS}"
    )


def _child_env(token: str) -> dict[str, str]:
    return dict(os.environ, DISCORD_TOKEN=token)


# ---- inventory --------------------------------------------------------------------------


def _list_cmd() -> list[str]:
    return [node_exe(), recorder_script(), "--list"]


def list_inventory(timeout_s: float = 20.0, token: str | None = None) -> dict:
    tok = get_token() if token is None else token.strip()
    if not tok:
        raise RecorderError("no_token", "No Discord bot token is set.")
    try:
        res = subprocess.run(
            _list_cmd(),
            env=_child_env(tok),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RecorderError("timeout", "Timed out talking to Discord.") from None
    except OSError as e:
        raise RecorderError("launch_failed", f"Could not start the recorder: {e}") from None
    for line in (res.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("event") == "inventory":
            return ev
        if ev.get("event") == "error":
            raise RecorderError(str(ev.get("code") or "error"), str(ev.get("message") or ""))
    raise RecorderError("timeout", "The recorder returned no inventory.")


# ---- the recorder process ---------------------------------------------------------------


class RecorderProcess:
    def __init__(
        self,
        out_dir: str,
        *,
        notice: str,
        channel_id: str | None,
        on_event: Callable[[dict], None],
        cmd: list[str] | None = None,
    ) -> None:
        self.out_dir = out_dir
        self.notice = notice
        self.channel_id = channel_id
        self.on_event = on_event
        self._cmd = cmd
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._err_reader: threading.Thread | None = None
        self._stderr: list[str] = []
        self._exit: int | None = None
        self._stopped = False
        self._lock = threading.Lock()

    @property
    def args(self) -> list[str]:
        return list(self._proc.args) if self._proc is not None else []  # type: ignore[arg-type]

    @property
    def stderr_lines(self) -> list[str]:
        return list(self._stderr)

    def start(self) -> None:
        env = os.environ.copy()
        if self._cmd is not None:
            cmd = list(self._cmd)
            if get_token():
                env["DISCORD_TOKEN"] = get_token()
        else:
            token = get_token()
            if not token:
                raise RecorderError("no_token", "No Discord bot token is set.")
            env["DISCORD_TOKEN"] = token
            cmd = [
                node_exe(),
                recorder_script(),
                "--record",
                "--out",
                self.out_dir,
                "--notice",
                self.notice,
            ]
            if self.channel_id:
                cmd += ["--channel", self.channel_id]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=_NO_WINDOW,
            )
        except OSError as e:
            raise RecorderError(
                "launch_failed", f"Could not start the recorder: {e.strerror or type(e).__name__}"
            ) from None
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._err_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._err_reader.start()

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if isinstance(ev, dict) and "event" in ev:
                    try:
                        self.on_event(ev)
                    except Exception as e:  # a bad handler must not kill the reader
                        config.log_exception("discord_recorder.on_event", e)
        except (OSError, ValueError):
            pass

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            for line in self._proc.stderr:
                if len(self._stderr) < _STDERR_CAP:
                    self._stderr.append(line.rstrip("\n"))
        except (OSError, ValueError):
            pass

    def _close_stdin(self) -> None:
        p = self._proc
        if p is None or p.stdin is None:
            return
        try:
            p.stdin.close()
        except (OSError, ValueError):
            pass

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._proc.poll() if self._proc is not None else None

    @property
    def readers_done(self) -> bool:
        """True once the stdout reader has consumed everything the child wrote."""
        return self._reader is None or not self._reader.is_alive()

    def request_stop(self) -> None:
        """Non-blocking stop request: tell the recorder to stop and close its stdin.

        Does not wait or kill; the recorder finishes by itself and leaves its .pcm files
        for recovery. Safe to call repeatedly and alongside stop()."""
        p = self._proc
        if p is None or p.stdin is None:
            return
        try:
            if p.poll() is None:
                p.stdin.write(_STOP_LINE)
                p.stdin.flush()
        except (OSError, ValueError):
            pass
        self._close_stdin()

    def stop(self, timeout_s: float = 15.0) -> int | None:
        """Ask the recorder to stop, wait, kill on timeout. Returns the exit code."""
        with self._lock:
            if self._stopped or self._proc is None:
                return self._exit
            p = self._proc
            if p.poll() is None and p.stdin is not None:
                try:
                    p.stdin.write('{"cmd":"stop"}\n')
                    p.stdin.flush()
                except (OSError, ValueError):
                    pass
            self._close_stdin()
            try:
                p.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                p.kill()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            for t in (self._reader, self._err_reader):
                if t is not None:
                    t.join(timeout=5)
            for stream in (p.stdout, p.stderr):
                try:
                    if stream:
                        stream.close()
                except (OSError, ValueError):
                    pass
            self._exit = p.poll()
            self._stopped = True
            return self._exit


# ---- finalize / recovery ----------------------------------------------------------------

_NAME_MAX = 80
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str) -> str:
    cleaned = _INVALID_NAME.sub("_", str(name or "")).strip()[:_NAME_MAX].strip()
    return cleaned or "user"


def finalize(out_dir: str, *, ffmpeg: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Convert each <userId>.pcm to <Name>_<userId>.wav (16 kHz mono). Returns (wavs, failures)."""
    ffmpeg = ffmpeg or audio.get_ffmpeg_path()
    names: dict = {}
    try:
        with open(os.path.join(out_dir, "tracks.json"), encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            names = loaded
    except (OSError, ValueError):
        pass
    wavs: list[str] = []
    failures: dict[str, str] = {}
    for pcm in sorted(Path(out_dir).glob("*.pcm")):
        uid = pcm.stem
        wav = pcm.with_name(f"{sanitize_name(names.get(uid) or uid)}_{uid}.wav")
        cmd = [ffmpeg, "-nostdin", "-f", "s16le", "-ar", "48000", "-ac", "1", "-i", str(pcm)]
        cmd += ["-ar", "16000", "-ac", "1", str(wav), "-y"]
        try:
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=_NO_WINDOW,
                check=False,
            )
        except OSError as e:
            failures[str(pcm)] = str(e)
            continue
        if res.returncode != 0 or not wav.exists():
            tail = (res.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
            failures[str(pcm)] = " | ".join(tail) or f"ffmpeg exited {res.returncode}"
            try:
                wav.unlink()
            except OSError:
                pass
            continue
        pcm.unlink()
        wavs.append(str(wav))
    return wavs, failures


def unfinished_recordings(root: str) -> list[str]:
    """Recording folders under root that still hold .pcm files (interrupted before finalize)."""
    try:
        entries = sorted(Path(root).iterdir())
    except OSError:
        return []
    return [str(d) for d in entries if d.is_dir() and any(d.glob("*.pcm"))]


def session_id_from_dir(path: str) -> int | None:
    m = re.match(r"^session_(\d+)_", os.path.basename(os.path.normpath(path)))
    return int(m.group(1)) if m else None
