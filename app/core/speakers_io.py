"""Read/write helpers for the speakers.json schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_FALLBACK_POLICY: dict[str, str] = {
    "unknown_speaker_label": "Unknown/Guest",
    "instructions": (
        "If a speaker cannot be confidently matched to any known player or "
        "non-player based on their speech content, assign them the label "
        "'Unknown/Guest' rather than guessing."
    ),
}


def empty_speakers_doc(campaign: str = "", context: str = "") -> dict[str, Any]:
    return {
        "campaign": campaign,
        "context": context,
        "known_non_players": [],
        "fallback_policy": dict(DEFAULT_FALLBACK_POLICY),
        "players": [],
    }


def load_speakers_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"speakers.json not found at {path}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("speakers.json must be a JSON object.")
    data.setdefault("campaign", "")
    data.setdefault("context", "")
    data.setdefault("known_non_players", [])
    data.setdefault("fallback_policy", dict(DEFAULT_FALLBACK_POLICY))
    data.setdefault("players", [])
    return data


def save_speakers_json(path: str, data: dict[str, Any]) -> None:
    import os
    import shutil

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: serialise to a temp file in the same directory, fsync, then
    # os.replace() — a crash mid-write can never truncate the real file. Keep a
    # single .bak of the prior version as a safety net.
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    if p.exists():
        try:
            shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
        except OSError:
            pass
    os.replace(tmp, p)


def profiles_to_speakers_doc(
    campaign: str,
    context: str,
    speakers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Transform UI-edited profiles into the speakers.json schema."""
    doc = empty_speakers_doc(campaign=campaign, context=context)
    for sp in speakers:
        included = bool(sp.get("include_in_tracking", 1))
        role = (sp.get("role") or "").strip()
        entry = {
            "player_name": sp.get("display_name", "") or sp.get("source_speaker_id", ""),
            "role": role or "Player",
            "character_name": sp.get("character_name", ""),
            "character_class": sp.get("character_class", ""),
            "notes": sp.get("notes", ""),
            "speech_patterns": sp.get("speech_patterns") or [],
            "source_speaker_id": sp.get("source_speaker_id", ""),
        }
        if not included or role == "Non-Player":
            non_player = {
                "name": entry["player_name"],
                "role": "ignore" if not included else (role or "Non-Player"),
                "notes": entry["notes"],
                "speech_patterns": entry["speech_patterns"],
                "source_speaker_id": entry["source_speaker_id"],
            }
            doc["known_non_players"].append(non_player)
        else:
            doc["players"].append(entry)
    return doc
