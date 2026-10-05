"""Fetch the pinned Node.js runtime into vendor/node (dev/build only).

The app never imports this. setup_venv.bat and build.bat run it; the recorder
helper (recorder/recorder.mjs) runs on this bundled node.exe, so end users need
no Node install. An already-installed matching runtime needs no network.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

NODE_VERSION = "24.21.0"
ZIP_NAME = f"node-v{NODE_VERSION}-win-x64.zip"
ZIP_SHA256 = "158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541"
URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{ZIP_NAME}"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "vendor" / "node"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_installed(dest: Path) -> bool:
    """True when node.exe and npm.cmd exist and node.exe reports the pinned version."""
    dest = Path(dest)
    node = dest / "node.exe"
    if not node.is_file() or not (dest / "npm.cmd").is_file():
        return False
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(  # noqa: S603  # nosec B603 - our own pinned binary
            [str(node), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() == f"v{NODE_VERSION}"


def download(url: str, path: Path) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError(f"refusing non-https URL: {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, open(path, "wb") as f:  # nosec B310
        shutil.copyfileobj(resp, f)


def extract(zip_path: Path, dest: Path) -> None:
    """Extract the zip into dest, flattening its single top-level folder."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            parts = info.filename.split("/", 1)
            rel = parts[1] if len(parts) == 2 else ""
            if not rel:
                continue
            target = (dest / rel).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe path in zip: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def main(argv: list[str] | None = None, *, dest: Path | None = None) -> int:
    dest = Path(dest or DEFAULT_DEST)
    if is_installed(dest):
        print(f"[fetch_node_runtime] OK — Node.js v{NODE_VERSION} already present at {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.parent / f"{ZIP_NAME}.part"
    print(f"[fetch_node_runtime] Downloading {URL}")
    try:
        download(URL, part)
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        print(f"[fetch_node_runtime] Download failed: {type(e).__name__}: {e}")
        return 1
    digest = sha256(part)
    if digest != ZIP_SHA256:
        part.unlink(missing_ok=True)
        print(
            f"[fetch_node_runtime] SHA-256 mismatch: expected {ZIP_SHA256}, got {digest}. "
            "The download was deleted."
        )
        return 1
    try:
        if dest.exists():
            shutil.rmtree(dest)
        extract(part, dest)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_node_runtime] Extract failed: {type(e).__name__}: {e}")
        return 1
    finally:
        part.unlink(missing_ok=True)
    if not is_installed(dest):
        print(f"[fetch_node_runtime] Installed runtime at {dest} did not report v{NODE_VERSION}")
        return 1
    print(f"[fetch_node_runtime] OK — fetched Node.js v{NODE_VERSION} to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
