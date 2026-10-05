"""Generate the exact, fully transitive library locks used by first-run setup.

Dev/release tool only; the app never imports it. First-run setup installs a lock
with ``pip install --no-deps -r locks/<profile>.txt``, so the lock must list every
package. Generate it from a clean, app-only venv (see locks/README.md):

    python scripts/make_locks.py --profile gpu --venv C:/cs-lock/gpu --out locks/gpu.txt
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import subprocess  # nosec B404 - runs our own venv python only
import sys
from pathlib import Path

INDEX_URLS = {
    "gpu": "https://download.pytorch.org/whl/cu128",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
TORCH_SUFFIX = {"gpu": "+cu128", "cpu": "+cpu"}
REQUIRED = ("whisperx", "pyannote-audio", "torch", "faster-whisper")
# Tooling that never belongs in a runtime lock.
ALWAYS_EXCLUDED = {"pip", "setuptools", "wheel", "torchvision"}
# Dev-only names that are nevertheless runtime dependencies of app packages
# (httpx is pulled in by anthropic/openai/google-genai).
RUNTIME_ALSO = {"httpx"}

REPO = Path(__file__).resolve().parents[1]


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "==" not in line:
        return None
    name, version = line.split("==", 1)
    return normalise(name), version.strip()


def render(
    freeze_lines: list[str],
    *,
    profile: str,
    python_version: str,
    pip_version: str,
    dev_only: set[str],
    date: str,
) -> str:
    """Render a lock file from ``pip list --format=freeze`` lines."""
    if profile not in INDEX_URLS:
        raise ValueError(f"unknown profile {profile!r}; expected 'gpu' or 'cpu'")
    skip = ALWAYS_EXCLUDED | {normalise(n) for n in dev_only}
    pkgs: dict[str, str] = {}
    for line in freeze_lines:
        parsed = _parse(line)
        if parsed is None:
            continue
        pkgs[parsed[0]] = parsed[1]
    missing = [n for n in REQUIRED if n not in pkgs]
    if missing:
        raise ValueError(f"required package(s) missing from freeze: {', '.join(missing)}")
    suffix = TORCH_SUFFIX[profile]
    for name in ("torch", "torchaudio"):
        version = pkgs.get(name)
        if version is None:
            raise ValueError(f"{name} missing from freeze")
        if not version.endswith(suffix):
            raise ValueError(f"{name}=={version} is not a {suffix} build (profile {profile})")
    body = [f"{n}=={v}" for n, v in sorted(pkgs.items()) if n not in skip]
    header = [
        f"# CampaignScribe {profile} lock \u2014 Python {python_version} \u2014 generated {date}",
        f"# pip=={pip_version}",
        f"--extra-index-url {INDEX_URLS[profile]}",
    ]
    return "\n".join([*header, *body]) + "\n"


def lock_sha256(path: str | Path) -> str:
    """SHA-256 of a lock file with CRLF normalised to LF (checkout-independent)."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def dev_only_names(root: Path = REPO) -> set[str]:
    """requirements-dev.txt top-level names that are not also in requirements.txt."""

    def names(p: Path) -> set[str]:
        out = set()
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = raw.split("#", 1)[0].strip()
            if not s or s.startswith("-"):
                continue
            m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", s)
            if m:
                out.add(normalise(m.group(0)))
        return out

    return names(root / "requirements-dev.txt") - names(root / "requirements.txt") - RUNTIME_ALSO


def _run(venv: Path, *args: str) -> str:
    exe = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(  # nosec B603 - fixed argv, our own venv python
        [str(exe), *args], capture_output=True, text=True, check=True, creationflags=flags
    ).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, choices=sorted(INDEX_URLS))
    ap.add_argument("--venv", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    freeze = _run(args.venv, "-m", "pip", "list", "--format=freeze", "--exclude-editable")
    pyver = _run(args.venv, "-c", "import platform;print(platform.python_version())").strip()
    pipver = _run(args.venv, "-m", "pip", "--version").split()[1]
    text = render(
        freeze.splitlines(),
        profile=args.profile,
        python_version=pyver,
        pip_version=pipver,
        dev_only=dev_only_names(),
        date=datetime.date.today().isoformat(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {args.out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
