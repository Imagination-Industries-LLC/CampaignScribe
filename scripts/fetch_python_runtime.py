"""Fetch the pinned official python.org Python 3.13 zip into vendor/python (build only).

The app never imports this. build_installer.bat runs it; the result is bundled
as {app}\\python by the installer. Already-valid files need no network.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VERSION = "3.13.16"
URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-amd64.zip"
ZIP_SHA256 = "bbf675bb5e763c1efbb09a3a461b259d81598a63c30c4b0d7ea11b9f063df159"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "vendor" / "python"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_installed(dest: Path, run=subprocess.run) -> bool:
    """True when dest holds a working python.exe of the pinned version with tkinter."""
    exe = Path(dest) / "python.exe"
    if not exe.is_file():
        return False
    kwargs = {"creationflags": _NO_WINDOW} if sys.platform == "win32" else {}
    try:
        res = run(
            [str(exe), "-c", "import sys, tkinter; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            timeout=60,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and (res.stdout or "").strip() == PY_VERSION


def download(url: str, part: Path) -> None:
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https URL: {url}")
    with urllib.request.urlopen(url, timeout=120) as r, open(part, "wb") as f:  # noqa: S310 - https enforced above
        shutil.copyfileobj(r, f)


def main(argv: list[str] | None = None, *, dest: Path | None = None) -> int:
    dest = Path(dest or DEFAULT_DEST)
    if is_installed(dest):
        print(f"[fetch_python_runtime] OK - Python {PY_VERSION} already present at {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.parent / (dest.name + ".zip.part")
    try:
        download(URL, part)
        digest = sha256(part)
        if digest != ZIP_SHA256:
            print(f"[fetch_python_runtime] Hash check FAILED: expected {ZIP_SHA256}, got {digest}")
            return 1
        if dest.exists():
            shutil.rmtree(dest)
        with zipfile.ZipFile(part) as z:
            z.extractall(dest)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_python_runtime] Download/extract failed: {type(e).__name__}: {e}")
        return 1
    finally:
        part.unlink(missing_ok=True)
    if not is_installed(dest):
        print(f"[fetch_python_runtime] Extracted runtime at {dest} failed its self-check")
        return 1
    print(f"[fetch_python_runtime] OK - fetched Python {PY_VERSION} to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
