"""Privacy disclosure text + constants (no Tk dependency).

PRIVACY.md (repo root) is the single source of truth; it is bundled into the
frozen app and read at runtime. A short embedded statement is used only if the
file can't be found (defensive — should not happen in a correct build).
"""

from __future__ import annotations

import sys
from pathlib import Path

ANTHROPIC_PRIVACY_URL = "https://www.anthropic.com/legal/privacy"
GEMINI_PRIVACY_URL = "https://ai.google.dev/gemini-api/terms"
OPENROUTER_PRIVACY_URL = "https://openrouter.ai/privacy"
PRIVACY_MD_URL = "https://github.com/Imagination-Industries-LLC/CampaignScribe/blob/main/PRIVACY.md"


def note_samples(vendor_label: str) -> str:
    return (
        f"Speaker samples are sent to {vendor_label} for this step. "
        "Learn more: Help → Privacy & Data."
    )


def note_transcript(vendor_label: str) -> str:
    return (
        f"Transcript text is sent to {vendor_label} for this step. "
        "Learn more: Help → Privacy & Data."
    )


# Defaults (the pre-Phase-2 wording) for callers that have no provider context.
NOTE_SAMPLES = note_samples("Anthropic (Claude)")
NOTE_TRANSCRIPT = note_transcript("Anthropic (Claude)")

_FALLBACK = (
    "CampaignScribe sends short transcript snippets and full transcript text to "
    "the AI provider you choose in Settings (Claude by default) to identify speakers "
    "and write summaries. Your audio, database, saved files, and API keys stay on your "
    "computer. No analytics or telemetry by default. See Help → Privacy & Data and "
    "PRIVACY.md for details."
)


def _privacy_md_path() -> Path:
    """Path to the bundled/dev PRIVACY.md."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[2]  # repo root
    return base / "PRIVACY.md"


def load_privacy_text() -> str:
    """Return the full privacy statement, or a short embedded fallback."""
    try:
        return _privacy_md_path().read_text(encoding="utf-8")
    except (OSError, ValueError):
        return _FALLBACK
