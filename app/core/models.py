"""Locate model files bundled with CampaignScribe (Tk-free).

Diarization weights live in <root>/models/speaker-diarization-community-1, where
<root> is the PyInstaller bundle dir when frozen, else the repo root. Presence
is checked on every run (cheap); content hashes are checked at fetch/build time
by scripts/fetch_diarization_weights.py.
"""

from __future__ import annotations

from pathlib import Path

from app.core import paths

DIARIZATION_DIRNAME = "speaker-diarization-community-1"
REQUIRED_FILES = (
    "config.yaml",
    "segmentation/pytorch_model.bin",
    "embedding/pytorch_model.bin",
    "plda/plda.npz",
    "plda/xvec_transform.npz",
)


class MissingModelError(RuntimeError):
    """A bundled model folder is absent or incomplete."""


def models_root() -> Path:
    return paths.app_home() / "models"


def diarization_dir() -> Path:
    d = models_root() / DIARIZATION_DIRNAME
    missing = [rel for rel in REQUIRED_FILES if not (d / rel).is_file()]
    if missing:
        raise MissingModelError(
            f"Speaker-diarization model files are missing from this installation "
            f"({', '.join(missing)}). Reinstall CampaignScribe, or in a development "
            f"checkout run: python scripts/fetch_diarization_weights.py"
        )
    return d
