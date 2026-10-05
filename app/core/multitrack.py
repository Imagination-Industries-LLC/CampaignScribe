"""One-file-per-speaker ("multi-track") transcription helpers (Tk-free).

Each input file is one person (Craig, the CampaignScribe Discord recorder, or
per-player mics), so no speaker detection is needed unless a track is a shared mic.
All tracks are assumed to start at the same moment.
"""

from __future__ import annotations

import os
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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


@dataclass
class MultitrackResult:
    segments: list[dict] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    durations: dict[str, float] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    embeddings: dict[str, Any] = field(default_factory=dict)


def transcribe_tracks(
    pipeline,
    tracks: list[Track],
    *,
    wav_for: Callable[[Track], str],
    shared_mic_count_kwargs: dict[str, Any] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> MultitrackResult:
    """Transcribe every track (one speaker each), relabel, merge. See module docstring."""
    res = MultitrackResult()
    per_track: list[list[dict]] = []
    diarized_embeddings: list[dict[str, Any]] = []

    def report(i: int, stage: str) -> None:
        if progress:
            progress(i, stage)

    for i, track in enumerate(tracks, start=1):
        label = track_label(i)
        wav: str | None = None
        try:
            report(i, "converting")
            wav = wav_for(track)
            try:
                res.durations[track.path] = wav_duration(wav)
            except Exception:  # noqa: BLE001, S110 - the length check is warning-only
                pass
            count_kwargs = (shared_mic_count_kwargs or {}) if track.shared_mic else {}
            segs = pipeline.transcribe_track(
                wav,
                diarize=track.shared_mic,
                progress=lambda stage, _pct, _i=i: report(_i, stage),
                **count_kwargs,
            )
            if track.shared_mic:
                order: list[str] = []
                for seg in segs:
                    sub = f"{label}_{seg['speaker']}"
                    if sub not in order:
                        order.append(sub)
                    seg["speaker"] = sub
                for n, sub in enumerate(order, start=1):
                    res.mapping[sub] = f"{track.speaker} ({n})"
                emb = getattr(pipeline, "_last_speaker_embeddings", None) or {}
                diarized_embeddings.append({f"{label}_{k}": v for k, v in emb.items()})
            else:
                for seg in segs:
                    seg["speaker"] = label
                res.mapping[label] = track.speaker
            per_track.append(segs)
            report(i, "complete")
        except InterruptedError:
            raise
        except Exception as e:  # noqa: BLE001 - one bad track must not sink the others
            res.failures[track.path] = f"{type(e).__name__}: {e}"[:200]
            report(i, "failed")
        finally:
            if wav and os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass

    res.segments = merge_segments(per_track)
    if len(diarized_embeddings) == 1:
        res.embeddings = diarized_embeddings[0]
    return res
