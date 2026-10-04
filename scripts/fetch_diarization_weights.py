"""Fetch the pinned pyannote community-1 diarization weights into models/ (dev/build only).

The app never imports this. setup_venv.bat and build.bat run it; it needs a
HuggingFace token once (HF_TOKEN env var, or the keyring entry the old app
Settings stored). Already-valid weights need no token and no network.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

REPO_ID = "pyannote/speaker-diarization-community-1"
REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
FILES: dict[str, str] = {
    "config.yaml": "5ce2bfa9a938dc132cec1172592d65173cbb8f444ea1e4133f10f9391de155be",
    "segmentation/pytorch_model.bin": "7ad24338d844fb95985486eb1a464e32d229f6d7a03c9abe60f978bacf3f816e",
    "embedding/pytorch_model.bin": "6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929",
    "plda/plda.npz": "9b77bcd840692710dd3496f62ecfeed8d8e5f002fd991b785079b244eab7d255",
    "plda/xvec_transform.npz": "325f1ce8e48f7e55e9c8aa47e05d2766b7c48c4b25b8de8dd751e7a4cc5fbe8f",
}
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "models" / "speaker-diarization-community-1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(dest: Path) -> list[str]:
    """Relative paths that are missing or have the wrong hash; [] means OK."""
    bad = []
    for rel, digest in FILES.items():
        p = Path(dest) / rel
        if not p.is_file() or sha256(p) != digest:
            bad.append(rel)
    return bad


def _token() -> str:
    tok = os.environ.get("HF_TOKEN", "").strip()
    if tok:
        return tok
    try:
        import keyring

        return (keyring.get_password("CampaignScribe", "huggingface_token") or "").strip()
    except Exception:  # noqa: BLE001 - no keyring backend is fine; we just have no token
        return ""


def fetch(dest: Path, token: str) -> None:
    from huggingface_hub import hf_hub_download

    for rel in FILES:
        src = hf_hub_download(REPO_ID, rel, revision=REVISION, token=token)
        target = Path(dest) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)  # real copy: no symlinks into the HF cache


def main(argv: list[str] | None = None, *, dest: Path | None = None) -> int:
    dest = Path(dest or DEFAULT_DEST)
    if not verify(dest):
        print(f"[fetch_diarization_weights] OK — weights already present at {dest}")
        return 0
    token = _token()
    if not token:
        print(
            "[fetch_diarization_weights] No HuggingFace token found.\n"
            "  1) Accept the license at https://huggingface.co/pyannote/speaker-diarization-community-1\n"
            "  2) Create a read token at https://huggingface.co/settings/tokens\n"
            "  3) Re-run with:  set HF_TOKEN=hf_...  then  python scripts\\fetch_diarization_weights.py"
        )
        return 2
    try:
        fetch(dest, token)
    except Exception as e:  # noqa: BLE001
        print(
            f"[fetch_diarization_weights] Download failed: {type(e).__name__}: {e}\n"
            "  If this is a 401/403, accept the license at "
            "https://huggingface.co/pyannote/speaker-diarization-community-1 "
            "with the same account as your token."
        )
        return 1
    bad = verify(dest)
    if bad:
        print(f"[fetch_diarization_weights] Hash check FAILED for: {', '.join(bad)}")
        return 1
    print(f"[fetch_diarization_weights] OK — fetched {REPO_ID}@{REVISION[:8]} to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
