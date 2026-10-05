"""One-file-per-speaker ("multi-track") transcription helpers (Tk-free).

Each input file is one person (Craig, the CampaignScribe Discord recorder, or
per-player mics), so no speaker detection is needed unless a track is a shared mic.
All tracks are assumed to start at the same moment.
"""

from __future__ import annotations

import os
import re
import wave
from dataclasses import dataclass

_CRAIG = re.compile(r"^\d+-(?P<name>.+?)_\d+$")
_RECORDER = re.compile(r"^(?P<name>.+?)_\d{15,}$")


@dataclass(frozen=True)
class Track:
    path: str
    speaker: str
    shared_mic: bool = False


def name_from_filename(path: str) -> str:
    """Best-guess speaker name from a per-speaker file name."""
    stem = os.path.splitext(os.path.basename(path))[0].strip()
    for pattern in (_CRAIG, _RECORDER):
        m = pattern.match(stem)
        if m:
            return m.group("name").replace("_", " ").strip()
    return stem.replace("_", " ").strip()


def track_label(index: int) -> str:
    """Stable speaker id for the index-th track (1-based): TRACK_01, TRACK_02, ..."""
    return f"TRACK_{index:02d}"


def merge_segments(per_track: list[list[dict]]) -> list[dict]:
    """All tracks' segments in one list, ordered by start time then track order."""
    keyed = [
        (float(seg.get("start") or 0.0), t, n, seg)
        for t, segs in enumerate(per_track)
        for n, seg in enumerate(segs)
    ]
    keyed.sort(key=lambda k: (k[0], k[1], k[2]))
    return [k[3] for k in keyed]


def duration_mismatch(durations: dict[str, float], tolerance_s: float = 2.0) -> str:
    """'' when all durations agree within tolerance; otherwise a one-line warning."""
    if len(durations) < 2:
        return ""
    shortest = min(durations, key=durations.get)
    longest = max(durations, key=durations.get)
    if durations[longest] - durations[shortest] <= tolerance_s:
        return ""
    return (
        f"Tracks differ in length ({os.path.basename(shortest)} "
        f"{durations[shortest]:.0f}s vs {os.path.basename(longest)} "
        f"{durations[longest]:.0f}s) — they may not start together, so the "
        "merged order could be off."
    )


def wav_duration(path: str) -> float:
    """Length in seconds of a PCM WAV file."""
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())
