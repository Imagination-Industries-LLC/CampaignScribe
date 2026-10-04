"""Third-party notices text (Tk-free). THIRD-PARTY-NOTICES.md is bundled like PRIVACY.md."""

from __future__ import annotations

import sys
from pathlib import Path

_FALLBACK = (
    "CampaignScribe bundles the pyannote speaker-diarization-community-1 model "
    "(CC-BY-4.0) and uses WhisperX, faster-whisper and CTranslate2. See "
    "THIRD-PARTY-NOTICES.md in the installation folder or the project repository "
    "for full attributions."
)


def _notices_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[2]
    return base / "THIRD-PARTY-NOTICES.md"


def load_notices_text() -> str:
    try:
        return _notices_path().read_text(encoding="utf-8")
    except (OSError, ValueError):
        return _FALLBACK
