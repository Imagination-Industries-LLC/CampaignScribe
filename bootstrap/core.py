"""First-run bootstrap logic: state file, launch/setup decision, GPU and disk checks, pip.

Standard library only (no Tk, no third-party packages): the ML libraries may not
exist yet when this runs. Everything here is pure or takes injectable callables
so it can be tested on any platform.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILES = ("gpu", "cpu")
STATE_FILENAME = "cs-setup.json"
HOME_ENV = "CAMPAIGNSCRIBE_HOME"
MAX_ENV_PATH_LEN = 80
HEADROOM_BYTES = 2 * 1024**3
_REQUIRED_BYTES = {"gpu": 6 * 1024**3, "cpu": int(1.6 * 1024**3)}
NVIDIA_SMI_TIMEOUT = 10
VERIFY_CODE = (
    "import torch, whisperx, pyannote.audio, faster_whisper; "
    "print(torch.__version__, torch.cuda.is_available())"
)

# subprocess.CREATE_NO_WINDOW exists only on Windows; 0x08000000 is its value.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def no_window_flags() -> int:
    """creationflags for every subprocess: CREATE_NO_WINDOW on Windows, 0 elsewhere."""
    return _CREATE_NO_WINDOW if sys.platform == "win32" else 0


# --- paths and state -------------------------------------------------------


def _local_app_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "CampaignScribe"


def env_dir() -> Path:
    return _local_app_root() / "env"


def state_path() -> Path:
    return env_dir() / STATE_FILENAME


def setup_log_path() -> Path:
    return _local_app_root() / "env-setup.log"


def read_state() -> dict | None:
    """The recorded state, or None if the file is missing, corrupt, or not an object."""
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_state(profile: str, lock_sha: str, python_ver: str) -> None:
    """Atomically record a verified install (temp file in the same dir, then os.replace)."""
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profile": profile, "lock_sha256": lock_sha, "python_version": python_ver}
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".cs-setup-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- lock files ------------------------------------------------------------


def lock_path(app_home: str | Path, profile: str) -> Path:
    return Path(app_home) / "locks" / f"{profile}.txt"


def lock_sha256(path: str | Path) -> str:
    """SHA-256 of a lock file with CRLF normalised to LF (checkout-independent)."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def lock_pip_version(path: str | Path) -> str | None:
    """The pip version pinned in the lock header (``# pip==X``), or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(10):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("# pip=="):
                    return line[len("# pip==") :].strip() or None
    except OSError:
        return None
    return None


# --- launch / setup decision -----------------------------------------------


def decide(
    state: dict | None,
    app_home: str | Path,
    env_python_exists: bool,
    requested_switch: str | None,
) -> tuple[str, str | None]:
    """Choose ("launch", profile), ("setup", default_profile_or_None) or ("resetup", profile).

    Only a state written after verification counts, so a partial environment
    (no state) always leads to setup. ``resetup`` is the same profile whose
    bundled lock changed (an upgrade).
    """
    if requested_switch in PROFILES:
        return ("setup", requested_switch)
    profile = state.get("profile") if isinstance(state, dict) else None
    if profile not in PROFILES:
        return ("setup", None)
    if not env_python_exists:
        return ("setup", profile)
    try:
        current = lock_sha256(lock_path(app_home, profile))
    except OSError:
        return ("resetup", profile)
    if state.get("lock_sha256") != current:
        return ("resetup", profile)
    return ("launch", profile)


# --- hardware, disk and path checks ----------------------------------------


def detect_nvidia(run=subprocess.run, which=shutil.which) -> dict:
    """Look for nvidia-smi (PATH, then System32) and parse the first GPU's name and driver."""
    result = {"found": False, "name": "", "driver": ""}
    exe = which("nvidia-smi")
    if not exe:
        system_root = os.environ.get("SystemRoot")
        if system_root:
            candidate = Path(system_root) / "System32" / "nvidia-smi.exe"
            if candidate.is_file():
                exe = str(candidate)
    if not exe:
        return result
    try:
        proc = run(
            [exe, "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=NVIDIA_SMI_TIMEOUT,
            creationflags=no_window_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return result
    if proc.returncode != 0:
        return result
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return result
    name, _, driver = lines[0].partition(",")
    result.update(found=True, name=name.strip(), driver=driver.strip())
    return result


def required_bytes(profile: str) -> int:
    """Disk needed for the profile plus 2 GiB headroom."""
    return _REQUIRED_BYTES[profile] + HEADROOM_BYTES


def disk_ok(path: str | Path, profile: str) -> tuple[bool, int]:
    """(enough free space?, free bytes) on the drive holding ``path`` (may not exist yet)."""
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    return free >= required_bytes(profile), free


def path_ok(path: str | Path) -> bool:
    """False if the env path is long enough to push torch DLL paths past MAX_PATH."""
    return len(str(path)) <= MAX_ENV_PATH_LEN


# --- commands --------------------------------------------------------------


def pip_upgrade_command(env_python: str | Path, version: str) -> list[str]:
    return [
        str(env_python),
        "-m",
        "pip",
        "install",
        "--require-virtualenv",
        "--disable-pip-version-check",
        f"pip=={version}",
    ]


def pip_command(env_python: str | Path, lock_file: str | Path) -> list[str]:
    return [
        str(env_python),
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--require-virtualenv",
        "--progress-bar",
        "off",
        "--disable-pip-version-check",
        "--retries",
        "5",
        "--timeout",
        "60",
        "-r",
        str(lock_file),
    ]


def verify_command(env_python: str | Path) -> list[str]:
    return [str(env_python), "-c", VERIFY_CODE]


def parse_verify(stdout: str) -> tuple[str, bool]:
    """(torch_version, cuda_available) from the verify output's last non-empty line."""
    lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty verify output")
    parts = lines[-1].split()
    if len(parts) != 2 or parts[1] not in ("True", "False"):
        raise ValueError(f"unexpected verify output: {lines[-1]!r}")
    return parts[0], parts[1] == "True"


def launch_command(
    env_pythonw: str | Path, app_home: str | Path, base_env: dict | None = None
) -> tuple[list[str], dict]:
    """The app launch command and its environment (CAMPAIGNSCRIBE_HOME set)."""
    env = dict(os.environ if base_env is None else base_env)
    env[HOME_ENV] = str(app_home)
    return [str(env_pythonw), str(Path(app_home) / "main.py")], env


# --- pip progress ----------------------------------------------------------


class ProgressCounter:
    """Turns pip's output into (done, total, current_package).

    One package produces ``Collecting`` then ``Downloading`` or ``Using cached``,
    so only ``Collecting`` advances the count (the others would triple-count).
    ``Installing collected packages`` and ``Successfully installed`` are the
    slow/final phases: the bar is held one short of full until pip reports success.
    """

    def __init__(self, total_lines: int):
        self.total = max(int(total_lines), 1)
        self.done = 0
        self.current: str | None = None

    def feed(self, line: str) -> tuple[int, int, str | None]:
        text = line.strip()
        name = None
        if text.startswith("Collecting "):
            rest = text[len("Collecting ") :].split()
            name = rest[0] if rest else None
            self.done = min(self.done + 1, max(self.total - 1, 0))
            self.current = name
        elif text.startswith("Installing collected packages"):
            self.done = max(self.done, self.total - 1)
            self.current = None
        elif text.startswith("Successfully installed"):
            self.done = self.total
            self.current = None
        return self.done, self.total, name
