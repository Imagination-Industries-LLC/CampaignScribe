# Multi-Track Import (Phase 4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transcribe a set of per-speaker audio files into one speaker-labeled transcript, with no AI naming step and optional per-track speaker detection, using the existing outputs and session flow.

**Architecture:**
- A Tk-free `app/core/multitrack.py` holds:
  - pure helpers for names, labels, merging and duration;
  - a `transcribe_tracks` orchestrator that drives a new `TranscriptionPipeline.transcribe_track` once per track.
- `TranscribeTab` gains a mode switch and a track table. Its worker gains a multi-track branch that writes the same output files and session rows as today.

**Tech Stack:** Python 3.11, Tkinter/ttk, WhisperX (faked in tests), pytest, ruff, bandit.

**Spec:** `docs/superpowers/specs/2026-10-05-multitrack-import-design.md`

## Global Constraints

**Environment and commits:**
- Run Python through `.venv\Scripts\python`. The shell is PowerShell 5.1: no `&&`; use `; if ($?) { ... }`.
- Commit messages are single-line, with no `Co-Authored-By` trailer and no AI attribution.
- Do not commit `CampaignScribe.spec` changes. If it shows as modified, run `git checkout -- CampaignScribe.spec`.

**Code rules:**
- No new runtime dependencies.
- Every subprocess call uses `CREATE_NO_WINDOW`. None is expected here: ffmpeg runs through the existing `audio.convert_to_wav`.
- The word "MeetingScribe" must not appear anywhere.
- Never write or delete keyring entries.

**Full gate before each task's commit:**
- `.venv\Scripts\python -m pytest -q`
- `.venv\Scripts\python -m ruff check app tests scripts`
- `.venv\Scripts\python -m ruff format app tests scripts`
- `.venv\Scripts\python -m bandit -q -r app -ll`

Ruff is scoped to these folders because an untracked local `.venv-pre-bump` folder may exist in the repo root.

**CI constraints:**
- CI installs only `requirements-dev.txt`, with no torch, whisperx, pyannote or fetched `models/`.
- New tests must not import those packages for real. Fake whisperx with `sys.modules` entries, as `tests/unit/test_transcriber_loading.py` does.
- No test may open a real modal that waits (`messagebox.*`, `simpledialog.*`, `wait_window`). Patch them.
- `tests/gui/conftest.py` already fakes the diarization weights and the first-run welcome.

**Spec values (verbatim):**
- Track labels are `TRACK_01`, `TRACK_02` and so on, zero-padded to 2 digits.
- Shared-mic sub-speaker ids are `f"{track_label}_{pyannote_label}"`. Their display names are `"<name> (1)"`, `"<name> (2)"`, in order of first appearance.
- Output names are `transcript_{run_ts}_tracks.json`, `speaker_mapping_{run_ts}_tracks.json` and `transcript_{run_ts}_tracks.txt`.
- Duration tolerance is 2.0 seconds.
- UI strings:
  - Mode radios: `Mixed recording` and `One file per speaker`.
  - Track table columns: `File`, `Speaker`, `Shared mic`. Values are `☐` and `☑`.
  - The edit button is `Edit track…`.
  - In multi-track mode the spinbox label is `# speakers per shared mic`.
  - Pre-flight errors: `Add at least two files (one per speaker), or switch to Mixed recording.` and `Give every track a speaker name.`

**Controller ruling (deviation from the spec text):**
- The duration check reads each track's length from the 16 kHz WAV that `convert_to_wav` already produces, using the standard-library `wave` module. ffmpeg-python's probe needs `ffprobe`, which is not bundled.
- The mismatch warning is therefore shown when the run finishes, in the status line, and the run is never blocked.

## Review Focus

1. **A track with no speech** (silent or near-silent). Expected: no crash, zero segments from that track, and its name still in the mapping. Task 3 pins this.
2. **One track failing** (corrupt file or ffmpeg error) while the others succeed. Expected: the row shows failed, the others still produce the merged transcript, and the failure is listed. Tasks 3 and 5 pin this.
3. **Cancel in the middle of track 2 of 3.** Expected: no outputs written, rows after the current one shown as cancelled, and no exception escaping the worker. Task 5 pins this.
4. **Two tracks with the same speaker name**, for example a player who recorded twice. Expected: both are kept as separate labels mapped to the same display name, and the transcript shows that name for both. Tasks 1 and 3 pin this.
5. **Switching back to Mixed mode after editing tracks.** Expected: the files are kept, the Mixed run behaves exactly as before, and no multi-track outputs are written. Task 4 pins this.

---

### Task 1: Pure multi-track helpers

**Files:**
- Create: `app/core/multitrack.py`
- Test: `tests/unit/test_multitrack.py`

**Interfaces:**
- Produces:
  - `Track(path: str, speaker: str, shared_mic: bool = False)`, a frozen dataclass.
  - `name_from_filename(path) -> str`
  - `track_label(index: int) -> str`, which is 1-based.
  - `merge_segments(per_track: list[list[dict]]) -> list[dict]`
  - `duration_mismatch(durations: dict[str, float], tolerance_s: float = 2.0) -> str`
  - `wav_duration(path) -> float`

- [ ] **Step 1: Write the failing tests**

```python
"""Pure helpers for one-file-per-speaker transcription."""

from __future__ import annotations

import wave

import pytest

from app.core import multitrack as mt


@pytest.mark.parametrize(
    "path, expected",
    [
        (r"C:\rec\1-mike_1234.flac", "mike"),          # Craig
        (r"C:\rec\12-Sarah Q_0.ogg", "Sarah Q"),       # Craig, space in name
        (r"C:\rec\Mike_1083839469700001892.wav", "Mike"),  # CampaignScribe recorder
        (r"C:\rec\Sarah.m4a", "Sarah"),                # plain
        (r"C:\rec\dungeon_master.wav", "dungeon master"),  # underscores -> spaces
        (r"C:\rec\take_2.wav", "take 2"),              # short trailing digits kept
        (r"C:\rec\  Bob  .wav", "Bob"),
    ],
)
def test_name_from_filename(path, expected):
    assert mt.name_from_filename(path) == expected


def test_track_label_is_one_based_and_padded():
    assert mt.track_label(1) == "TRACK_01"
    assert mt.track_label(12) == "TRACK_12"


def test_merge_orders_by_start_then_track_order():
    a = [{"start": 1.0, "end": 2.0, "text": "a1", "speaker": "TRACK_01"},
         {"start": 5.0, "end": 6.0, "text": "a2", "speaker": "TRACK_01"}]
    b = [{"start": 1.0, "end": 1.5, "text": "b1", "speaker": "TRACK_02"},
         {"start": 3.0, "end": 4.0, "text": "b2", "speaker": "TRACK_02"}]
    merged = mt.merge_segments([a, [], b])
    assert [s["text"] for s in merged] == ["a1", "b1", "b2", "a2"]


def test_merge_handles_missing_start_as_zero():
    merged = mt.merge_segments([[{"start": None, "end": 1, "text": "x", "speaker": "TRACK_01"}]])
    assert merged[0]["text"] == "x"


def test_duration_mismatch():
    assert mt.duration_mismatch({"a.wav": 3600.0, "b.wav": 3601.5}) == ""
    msg = mt.duration_mismatch({"a.wav": 3600.0, "b.wav": 3500.0})
    assert "b.wav" in msg and "a.wav" in msg
    assert mt.duration_mismatch({}) == ""


def test_wav_duration(tmp_path):
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * 3)
    assert mt.wav_duration(str(p)) == pytest.approx(3.0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_multitrack.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.multitrack'`.

- [ ] **Step 3: Implement**

`app/core/multitrack.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_multitrack.py -v`
Expected: all pass. If `take_2` or another case disagrees with the regexes, fix the regex, not the test. The tests are the spec's intent: short trailing numbers are part of a name, Craig's `<n>-name_<digits>` form is stripped, and 15 or more trailing digits are a Discord id.

- [ ] **Step 5: Full gate, commit**

```
git add app/core/multitrack.py tests/unit/test_multitrack.py
git commit -m "feat: multi-track helpers (names from filenames, track labels, merge, duration check)"
```

---

### Task 2: `TranscriptionPipeline.transcribe_track`

**Files:**
- Modify: `app/core/transcriber.py`. Change `transcribe_file` at about lines 197-251 and add the new method.
- Test: `tests/unit/test_transcriber_track.py`

**Interfaces:**
- Produces: `TranscriptionPipeline.transcribe_track(wav_path, *, diarize=False, num_speakers=None, min_speakers=None, max_speakers=None, progress=None) -> list[dict]`. The keys are exactly `start, end, text, speaker`.
  - When `diarize=False`, every speaker is `"SPEAKER_00"`.
  - `_last_speaker_embeddings` is reset to `{}` at the start of every call, and set only by a diarized call.
- `transcribe_file`'s signature and behavior are unchanged.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_transcriber_track.py`. Build fakes like `tests/unit/test_transcriber_loading.py` does: a fake `whisperx` module in `sys.modules` and a fake `whisperx.diarize`. Then:
- monkeypatch `models.diarization_dir` to return `tmp_path`;
- monkeypatch `transcriber.check_gpu` to report no CUDA;
- give the fake `load_model` a model whose `.transcribe(path, batch_size=16)` returns `{"language": "en", "segments": [{"start": 0.0, "end": 1.0, "text": " hi "}]}`;
- make `load_align_model` return `(object(), {})` and `align(segs, *a)` return `{"segments": segs}`;
- give the fake `DiarizationPipeline` a `__call__` that records each call and returns `("DIAR", {"SPEAKER_00": [0.1, 0.2]})` when `return_embeddings=True`;
- make `assign_word_speakers(diar, result)` return `{"segments": [dict(s, speaker="SPEAKER_01") for s in result["segments"]]}`.

The tests:

```python
def test_track_without_diarize_never_calls_pyannote(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    segs = p.transcribe_track("x.wav")
    assert segs == [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00"}]
    assert fakes.diarize_calls == []
    assert p._last_speaker_embeddings == {}


def test_track_with_diarize_matches_transcribe_file(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    a = p.transcribe_track("x.wav", diarize=True, min_speakers=2, max_speakers=3)
    b = p.transcribe_file("x.wav", min_speakers=2, max_speakers=3)
    assert a == b == [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_01"}]
    assert fakes.diarize_calls[0]["min_speakers"] == 2


def test_embeddings_reset_between_tracks(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p.transcribe_track("x.wav", diarize=True)
    assert p._last_speaker_embeddings  # set by the diarized track
    p.transcribe_track("y.wav")
    assert p._last_speaker_embeddings == {}


def test_models_load_once_across_tracks(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p.transcribe_track("x.wav")
    p.transcribe_track("y.wav")
    assert fakes.load_model_calls == 1


def test_progress_can_cancel(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")

    def cb(stage, pct):
        if stage == "Transcribing":
            raise InterruptedError("Cancelled")

    with pytest.raises(InterruptedError):
        p.transcribe_track("x.wav", progress=cb)
```

Write the `fakes` fixture to expose `diarize_calls` (a list of kwargs dicts) and `load_model_calls` (an int). The test expectations above are the requirements. Adapt the fake plumbing to the real call shapes in `transcriber.py`, for example `coerce_embeddings` converting lists to arrays.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_transcriber_track.py -v`
Expected: FAIL with `AttributeError: ... 'transcribe_track'`.

- [ ] **Step 3: Implement without duplication**

Refactor `transcribe_file` into three private steps and reuse them:

```python
    def _transcribe_and_align(self, wav_path, progress):
        """Load models, Whisper-transcribe and align. Returns the aligned whisperx result."""
        import whisperx

        if progress:
            progress("Loading models", 0.05)
        self._load_models()
        if progress:
            progress("Transcribing", 0.20)
        result = self._model.transcribe(wav_path, batch_size=16)
        language = result.get("language", "en")
        if progress:
            progress("Aligning timestamps", 0.55)
        if language not in self._align_cache:
            model_a, metadata = whisperx.load_align_model(
                language_code=language, device=self.device
            )
            self._align_cache[language] = (model_a, metadata)
        model_a, metadata = self._align_cache[language]
        return whisperx.align(result["segments"], model_a, metadata, wav_path, self.device)

    def _diarize_into(self, wav_path, result, kwargs, progress):
        """Run pyannote and assign speakers to result's segments (stores embeddings)."""
        import whisperx

        if progress:
            progress("Diarizing speakers", 0.75)
        try:
            diarize_segments, _spk_emb = self._diarize(wav_path, return_embeddings=True, **kwargs)
            self._last_speaker_embeddings = coerce_embeddings(_spk_emb)
        except Exception:  # noqa: BLE001 - embeddings are best-effort; never break the transcript
            diarize_segments = self._diarize(wav_path, **kwargs)  # proven path, no embeddings
            self._last_speaker_embeddings = {}
        return whisperx.assign_word_speakers(diarize_segments, result)

    @staticmethod
    def _normalize(result, default_speaker="UNKNOWN"):
        return [
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": (seg.get("text") or "").strip(),
                "speaker": seg.get("speaker") or default_speaker,
            }
            for seg in result.get("segments", [])
        ]
```

`transcribe_file` becomes:

```python
        result = self._transcribe_and_align(wav_path, progress)
        kwargs = speaker_count_window(num_speakers, min_speakers, max_speakers)
        result = self._diarize_into(wav_path, result, kwargs, progress)
        if progress:
            progress("Done", 1.0)
        return self._normalize(result)
```

Keep its docstring and signature.

`transcribe_track`:

```python
    def transcribe_track(
        self,
        wav_path: str,
        *,
        diarize: bool = False,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        progress: Callable[[str, float], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Transcribe ONE speaker's track. No pyannote unless ``diarize`` (shared mic)."""
        self._last_speaker_embeddings = {}
        result = self._transcribe_and_align(wav_path, progress)
        if diarize:
            kwargs = speaker_count_window(num_speakers, min_speakers, max_speakers)
            result = self._diarize_into(wav_path, result, kwargs, progress)
            default = "UNKNOWN"
        else:
            default = "SPEAKER_00"
            for seg in result.get("segments", []):
                seg.pop("speaker", None)
        if progress:
            progress("Done", 1.0)
        return self._normalize(result, default_speaker=default)
```

- [ ] **Step 4: Run the new tests and the existing transcriber tests**

Run: `.venv\Scripts\python -m pytest tests/unit/test_transcriber_track.py tests/unit/test_transcriber_loading.py tests/unit/test_transcriber_count_window.py -v`
Expected: all pass.

- [ ] **Step 5: Full gate, commit**

```
git add app/core/transcriber.py tests/unit/test_transcriber_track.py
git commit -m "feat: TranscriptionPipeline.transcribe_track (per-speaker track, optional diarization)"
```

---

### Task 3: `transcribe_tracks` orchestrator

**Files:**
- Modify: `app/core/multitrack.py`
- Test: `tests/unit/test_multitrack_run.py`

**Interfaces:**
- Consumes: `Track`, `track_label`, `merge_segments` and `wav_duration` from Task 1; `pipeline.transcribe_track(...)` and `pipeline._last_speaker_embeddings` from Task 2.
- Produces:

```python
@dataclass
class MultitrackResult:
    segments: list[dict]            # merged, relabelled
    mapping: dict[str, str]         # speaker id -> display name (every successful track appears)
    durations: dict[str, float]     # track path -> seconds (successful conversions)
    failures: dict[str, str]        # track path -> short error text
    embeddings: dict[str, Any]      # diarized sub-speaker id -> embedding (only when exactly one track was diarized)

def transcribe_tracks(pipeline, tracks, *, wav_for, shared_mic_count_kwargs=None,
                      progress=None) -> MultitrackResult
```

  `progress(track_index: int, stage: str)` uses a 1-based index. Stages are `"converting"`, the pipeline's own stage names, and then `"complete"` or `"failed"`. The callback may raise `InterruptedError`, which propagates out of `transcribe_tracks` after the current temp WAV is deleted.

- [ ] **Step 1: Write the failing tests**

```python
"""transcribe_tracks: per-track transcription, relabel, merge, failures, cancel."""

from __future__ import annotations

import os

import pytest

from app.core import multitrack as mt


def _orig(wav: str) -> str:
    """Temp wav 'x/a.flac.tmp.wav' -> original track name 'a.flac'."""
    return os.path.basename(wav)[: -len(".tmp.wav")]


class FakePipeline:
    def __init__(self, canned, fail=(), diar_emb=None):
        self.canned = canned              # original file name -> list of (start, text, speaker)
        self.fail = set(fail)             # original file names that raise
        self.diar_emb = diar_emb or {}
        self.calls = []
        self._last_speaker_embeddings = {}

    def transcribe_track(self, wav, *, diarize=False, progress=None, **kw):
        name = _orig(wav)
        self.calls.append((name, diarize, kw))
        self._last_speaker_embeddings = {}
        if progress:
            progress("Transcribing", 0.2)
        if name in self.fail:
            raise RuntimeError("bad audio")
        if diarize:
            self._last_speaker_embeddings = dict(self.diar_emb)
        return [
            {"start": s, "end": s + 1, "text": t, "speaker": spk if diarize else "SPEAKER_00"}
            for s, t, spk in self.canned.get(name, [])
        ]


@pytest.fixture
def wav_for(tmp_path, monkeypatch):
    made = []

    def _wav_for(track):
        p = tmp_path / (os.path.basename(track.path) + ".tmp.wav")
        p.write_bytes(b"x")
        made.append(str(p))
        return str(p)

    monkeypatch.setattr(mt, "wav_duration", lambda p: 60.0)
    _wav_for.made = made
    return _wav_for


def _tracks():
    return [mt.Track("a.flac", "Mike"), mt.Track("b.flac", "Sarah")]


def test_relabel_merge_and_mapping(wav_for):
    pipe = FakePipeline({"a.flac": [(5.0, "a2", None), (1.0, "a1", None)],
                         "b.flac": [(2.0, "b1", None)]})
    res = mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for)
    assert [(s["text"], s["speaker"]) for s in res.segments] == [
        ("a1", "TRACK_01"), ("b1", "TRACK_02"), ("a2", "TRACK_01")]
    assert res.mapping == {"TRACK_01": "Mike", "TRACK_02": "Sarah"}
    assert res.failures == {}
    assert res.durations == {"a.flac": 60.0, "b.flac": 60.0}
    assert all(not os.path.exists(p) for p in wav_for.made)  # temp wavs deleted
```

Add these tests in the same style:

- `test_silent_track_keeps_name_in_mapping`: a track with zero segments still appears in `mapping` and in `durations`.
- `test_failed_track_is_reported_and_others_continue`: `b.flac` raises. The result has `a`'s segments, `failures == {"b.flac": "RuntimeError: bad audio"}`, `"TRACK_02" not in mapping`, and the temp WAV is deleted.
- `test_shared_mic_track_gets_sub_speakers`: `Track("b.flac", "Sarah", shared_mic=True)` returns segments with speakers `SPEAKER_01, SPEAKER_00, SPEAKER_01`.
  - Expect the ids `TRACK_02_SPEAKER_01` and `TRACK_02_SPEAKER_00`.
  - Expect the names `Sarah (1)` for `TRACK_02_SPEAKER_01` and `Sarah (2)` for `TRACK_02_SPEAKER_00`, numbered by first appearance.
  - Check that `pipeline.calls` shows `diarize=True` with `shared_mic_count_kwargs` passed through.
  - With a single diarized track whose fake embeddings are `{"SPEAKER_00": [1.0], "SPEAKER_01": [2.0]}`, expect `embeddings == {"TRACK_02_SPEAKER_00": [1.0], "TRACK_02_SPEAKER_01": [2.0]}`.
- `test_two_diarized_tracks_stash_no_embeddings`: `embeddings == {}`.
- `test_same_name_on_two_tracks_kept_separate`: both map to "Mike" under `TRACK_01` and `TRACK_02`.
- `test_cancel_propagates_and_cleans_temp`: progress raises `InterruptedError` on track 2. `transcribe_tracks` raises `InterruptedError`, and no temp WAV is left behind.
- `test_progress_reports_converting_and_complete`: record the `(index, stage)` calls. Each track gets `"converting"` first and `"complete"` last.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_multitrack_run.py -v`
Expected: FAIL with `AttributeError: module 'app.core.multitrack' has no attribute 'transcribe_tracks'`.

- [ ] **Step 3: Implement** (append to `app/core/multitrack.py`; add `from dataclasses import dataclass, field` and `from typing import Any, Callable`)

```python
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
            res.durations[track.path] = wav_duration(wav)
            segs = pipeline.transcribe_track(
                wav,
                diarize=track.shared_mic,
                progress=lambda stage, _pct, _i=i: report(_i, stage),
                **(shared_mic_count_kwargs or {} if track.shared_mic else {}),
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
```

Watch the precedence in the `**(...)` expression. Write it unambiguously as `**((shared_mic_count_kwargs or {}) if track.shared_mic else {})`. A shared-mic track with zero segments gets no mapping entry. That is acceptable, because no speaker was detected.

If the `"failed"` report itself raises `InterruptedError`, let it propagate.

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/unit/test_multitrack_run.py tests/unit/test_multitrack.py -v`
Expected: all pass.

- [ ] **Step 5: Full gate, commit**

```
git add app/core/multitrack.py tests/unit/test_multitrack_run.py
git commit -m "feat: transcribe_tracks orchestrator (relabel, merge, shared mic, failures, cancel)"
```

---

### Task 4: Transcribe tab mode switch and track table

**Files:**
- Modify: `app/ui/transcribe_tab.py`
  - The audio-file area is around lines 76-84. The model and speakers row is around 86-100.
  - Also change `_add_files`, `_remove_files`, `_clear_files` and `_start`'s pre-flights.
- Test: `tests/gui/test_multitrack_tab.py`

**Interfaces:**
- Consumes: `multitrack.Track` and `name_from_filename` (Task 1).
- Produces:
  - `TranscribeTab.mode_var`, a `tk.StringVar` holding `"mixed"` or `"tracks"`.
  - `TranscribeTab.track_meta: dict[str, dict]`, which maps a path to `{"speaker": str, "shared_mic": bool}`.
  - `TranscribeTab.tracks_table`, a `ttk.Treeview` with `iid = path`.
  - `TranscribeTab._tracks() -> list[multitrack.Track]`, in `audio_files` order.
  - `TranscribeTab._set_track(path, speaker=None, shared_mic=None)`, which updates both the metadata and the row.
  - `TranscribeTab.edit_track_btn`.
  - `TranscribeTab._apply_mode()`, which shows or hides the widgets.

- [ ] **Step 1: Write the failing GUI tests**

Use the `root` and tab fixture pattern from `tests/gui/test_missing_weights_preflight.py`: `TranscribeTab(root, types.SimpleNamespace(notebook=None))`. Patch `filedialog.askopenfilenames` in `app.ui.transcribe_tab` to return paths. Patch `messagebox.showerror` to record calls. Patch `threading.Thread.start` to record calls instead of running.

```python
def test_mode_switch_shows_track_table(tab):
    assert tab.mode_var.get() == "mixed"
    assert tab.tracks_table.winfo_manager() == ""
    tab.mode_var.set("tracks"); tab._apply_mode()
    assert tab.tracks_table.winfo_manager() == "grid"
    assert tab.files_box.winfo_manager() == ""
    assert tab.spk_label.cget("text") == "# speakers per shared mic"


def test_adding_files_prefills_names(tab, pick):
    tab.mode_var.set("tracks"); tab._apply_mode()
    pick([r"C:\r\1-mike_1234.flac", r"C:\r\Sarah.m4a"])
    tab._add_files()
    rows = [tab.tracks_table.item(i, "values") for i in tab.tracks_table.get_children()]
    assert rows == [("1-mike_1234.flac", "mike", "☐"), ("Sarah.m4a", "Sarah", "☐")]


def test_set_track_updates_row_and_meta(tab, pick):
    tab.mode_var.set("tracks"); tab._apply_mode()
    pick([r"C:\r\a.wav"]); tab._add_files()
    tab._set_track(r"C:\r\a.wav", speaker="Mike", shared_mic=True)
    assert tab.tracks_table.item(r"C:\r\a.wav", "values") == ("a.wav", "Mike", "☑")
    assert tab._tracks()[0] == multitrack.Track(r"C:\r\a.wav", "Mike", True)


def test_switching_back_to_mixed_keeps_files(tab, pick):
    tab.mode_var.set("tracks"); tab._apply_mode()
    pick([r"C:\r\a.wav", r"C:\r\b.wav"]); tab._add_files()
    tab.mode_var.set("mixed"); tab._apply_mode()
    assert list(tab.files_box.get(0, "end")) == [r"C:\r\a.wav", r"C:\r\b.wav"]
    assert tab.spk_label.cget("text") == "# speakers:"


def test_preflight_needs_two_tracks(armed_tab, errors, started):
    armed_tab.mode_var.set("tracks"); armed_tab._apply_mode()
    armed_tab.audio_files = [r"C:\r\a.wav"]; armed_tab.track_meta = {r"C:\r\a.wav": {"speaker": "A", "shared_mic": False}}
    armed_tab._start()
    assert errors == ["Add at least two files (one per speaker), or switch to Mixed recording."]
    assert started == []


def test_preflight_needs_names(armed_tab, errors, started):
    ...  # two tracks, one with speaker "  " → ["Give every track a speaker name."], no thread
```

The `armed_tab` fixture passes the earlier pre-flights. It sets `tab.speakers_path` to an existing temp file, saves a provider key with `config.save_provider_key("anthropic", "k")`, and sets `tab.out_var` to `tmp_path`. Remove-files and clear-all must also remove the `track_meta` entries and table rows. Add one test for each.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_multitrack_tab.py -v`
Expected: FAIL with `AttributeError` on `mode_var` or `tracks_table`.

- [ ] **Step 3: Implement**

- **Mode radios.** Add the two radios (`Mixed recording` → `"mixed"`, `One file per speaker` → `"tracks"`) in a small frame on the "Audio files:" row. Keep the label in column 0 and place the frame above the list. Shifting the grid rows down by one is fine, as long as later rows keep their relative order. `command=self._apply_mode` on each radio.
- **Track table.** Create `self.tracks_table = ttk.Treeview(body, columns=("file", "speaker", "shared"), show="headings", height=4)` with headings `File`, `Speaker` and `Shared mic`. Grid it in the same cell as `files_box`, then `grid_remove()` it. Bind `<Double-1>` to `self._edit_track`.
- **Edit button.** Add `self.edit_track_btn = ttk.Button(bcol, text="Edit track…", command=self._edit_track)`. It is packed only in tracks mode; `_apply_mode` handles `pack()` and `pack_forget()`.
- **Spinbox label.** Keep a reference: `self.spk_label = ttk.Label(body, text="# speakers:")`.
- `_apply_mode()`:
  - In `tracks` mode, hide `files_box`, show `tracks_table`, pack the edit button and set `spk_label` to `# speakers per shared mic`.
  - In `mixed` mode, do the reverse and set `spk_label` to `# speakers:`.
  - Never clear `audio_files`.
- **File buttons.** `_add_files`, `_remove_files` and `_clear_files` keep updating `audio_files` and `files_box` exactly as today. In addition, each also updates `track_meta` and `tracks_table`:
  - On add: `track_meta.setdefault(p, {"speaker": name_from_filename(p), "shared_mic": False})`, then insert a row with `iid=p`.
  - Remove-selected must work from whichever widget is visible. In tracks mode, the selection comes from `tracks_table.selection()`, whose items are the paths.
  - Keep the two views in sync through one private helper.
  - `_set_audio_files`, which loads a session, also rebuilds the track table, with names from filenames.
- `_set_track(path, speaker=None, shared_mic=None)` updates `track_meta[path]` and the row's values.
- `_edit_track()` opens a small `tk.Toplevel`, transient and grab-set. It contains:
  - a `ttk.Combobox` whose values are the campaign's player names, editable. Read them with `library.get_current_doc(self.active_slug).get("players", [])` and each `player_name`, wrapped in `try/except Exception` that falls back to `[]`.
  - a `Shared mic` checkbutton.
  - OK and Cancel buttons. OK calls `_set_track` and destroys the window.

  The GUI tests don't open this dialog. They test `_set_track` directly. Add one test that constructs the dialog, sets its fields, invokes OK, and checks the row. Reach the widgets through attributes you expose on the dialog object, and never call `wait_window`.
- `_tracks()` returns `[multitrack.Track(p, track_meta[p]["speaker"].strip(), track_meta[p]["shared_mic"]) for p in audio_files]`.
- **Pre-flights in `_start`.** After the existing "Add at least one audio file." check, and only in tracks mode, check for at least two tracks and for blank names, with the exact messages from Global Constraints. All other pre-flights stay in their current order.

- [ ] **Step 4: Run the new tests and the existing Transcribe GUI tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_multitrack_tab.py tests/gui/test_missing_weights_preflight.py tests/gui/test_stage_tabs_session.py tests/gui/test_cold_start_onramp.py tests/gui/test_ui_scroll_protection.py -v`
Expected: all pass.

- [ ] **Step 5: Full gate, commit**

```
git add app/ui/transcribe_tab.py tests/gui/test_multitrack_tab.py
git commit -m "feat: Transcribe tab 'One file per speaker' mode with track table and pre-flights"
```

---

### Task 5: Multi-track run path in the worker

**Files:**
- Modify: `app/ui/transcribe_tab.py`. Change `_start` (where rows are reset and the thread starts), `_worker`, and `_persist_detected_speakers`.
- Test: `tests/gui/test_multitrack_run.py`

**Interfaces:**
- Consumes:
  - `multitrack.transcribe_tracks`, `MultitrackResult` and `duration_mismatch` (Tasks 1 and 3);
  - `TranscribeTab._tracks()` and `mode_var` (Task 4);
  - `pipeline.transcribe_track` (Task 2).
- Produces:
  - `TranscribeTab._persist_detected_speakers(session_id, segments, names: dict[str, str] | None = None)`. With `names`, each new row's `display_name` is `names.get(label, "")`.
  - `TranscribeTab._worker_tracks(provider, speakers_doc, ignored_ids, pipeline, run_ts)`. It is called from `_worker` in tracks mode.

- [ ] **Step 1: Write the failing tests**

`tests/gui/test_multitrack_run.py` runs the worker **synchronously** on the main thread. Patch `threading.Thread` in `app.ui.transcribe_tab` with a class whose `start()` calls `target()` directly. Patch `tab.after` to call the callback immediately: `lambda ms, fn=None, *a: fn(*a) if fn else None`. Then patch:
- `transcriber.TranscriptionPipeline` in `app.ui.transcribe_tab` with a fake whose `transcribe_track(wav, diarize=False, progress=None, **kw)` returns canned segments keyed by the WAV name, and whose `close()` is a no-op;
- `audio.convert_to_wav` to copy a tiny real WAV into tmp and return its path;
- `speaker_id.identify_speakers` with a function that **fails the test** if called;
- `speaker_id.refine_speakers` to return `{"improvements": [], "new_speakers": [], "suggested_ignores": []}`;
- `llm.get_provider` to return `object()`;
- `llm.provider_ready` to return True.

Create a session with `db.init_db()` and `db.create_session("S")`, and select it by setting `tab._session_index` and the combobox, following the pattern in `test_stage_tabs_session.py`. Alternatively set `tab.session_id` after `_start` resolves it. The tests:

- `test_tracks_run_writes_outputs_and_names_speakers`: with tracks `Mike` and `Sarah`:
  - the output folder contains exactly one each of `transcript_*_tracks.json`, `speaker_mapping_*_tracks.json`, `transcript_*_tracks.txt` and `speakers_improvements_*.json`;
  - the mapping JSON is `{"TRACK_01": "Mike", "TRACK_02": "Sarah"}`;
  - the `.txt` contains `Mike:` and `Sarah:` lines in time order;
  - `db.get_speakers_for_session(sid)` has rows `TRACK_01/Mike` and `TRACK_02/Sarah`;
  - the session status is `"transcribed"` and `num_speakers_detected` is 2;
  - `source_audio_files` holds the two paths.
- `test_failed_track_row_marked_and_rest_written`: the second track's convert raises. Its tree row state is failed, and the outputs still exist with only Mike.
- `test_all_tracks_failed_writes_nothing`: no `transcript_*` files are written.
- `test_cancel_mid_run_writes_nothing`: set `tab._cancel` from inside the fake's `transcribe_track` on track 2. Expect no `transcript_*_tracks.*` files, no exception, and `_busy` False afterwards.
- `test_duration_mismatch_warns_in_status`: the fake WAVs have different lengths. The status text contains "may not start together", and the outputs are still written.
- `test_mixed_mode_unchanged`: in Mixed mode, the fake pipeline's `transcribe_file` is called and `transcribe_track` is never called.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_multitrack_run.py -v`

- [ ] **Step 3: Implement**

**In `_start`:**
- When resetting rows in tracks mode, the per-file rows are the track paths, as today.
- Store `self._run_mode = self.mode_var.get()` before starting the thread, so a mid-run toggle cannot change the branch.

**In `_worker`,** after `pipeline` is built and `run_ts` is computed: if `self._run_mode == "tracks"`, call `self._worker_tracks(provider, speakers_doc, ignored_ids, pipeline, run_ts)`, then run the existing `pipeline.close()` and `_set_busy(False)` tail, and return. Restructure only as much as needed so the close and busy cleanup run once in both branches, in a `try/finally`. The Mixed branch keeps its existing body unchanged.

**`_worker_tracks`:**

```python
    def _worker_tracks(self, provider, speakers_doc, ignored_ids, pipeline, run_ts):
        tracks = self._tracks()
        count_kwargs = transcriber.diarization_run_kwargs(
            self._run_params.get("expected_count"), int(self.spk_var.get())
        )

        def progress(i: int, stage: str) -> None:
            if self._cancel.is_set():
                raise InterruptedError("Cancelled")
            path = tracks[i - 1].path
            state = {"converting": "converting", "complete": "complete", "failed": "failed"}.get(
                stage, "transcribing"
            )
            self._set_row(path, state, "" if state != "transcribing" else stage)
            self._set_status(f"[{i}/{len(tracks)}] {os.path.basename(path)} — {stage}")

        try:
            res = multitrack.transcribe_tracks(
                pipeline,
                tracks,
                wav_for=lambda t: audio.convert_to_wav(t.path),
                shared_mic_count_kwargs=count_kwargs,
                progress=progress,
            )
        except InterruptedError:
            for t in tracks:
                if self.row_items.get(t.path) and self.tree.set(self.row_items[t.path], "state") not in ("complete",):
                    self._set_row(t.path, "failed", "cancelled")
            self._set_status("Cancelled — nothing written.")
            return

        for path, err in res.failures.items():
            config.log_exception(f"transcribe_tab[tracks:{os.path.basename(path)}]", RuntimeError(err))
            self._set_row(path, "failed", err[:100])
        if not res.mapping:
            self._set_status("All tracks failed — nothing written.")
            return

        json_path = os.path.join(self.output_dir, f"transcript_{run_ts}_tracks.json")
        transcriber.save_segments_json(res.segments, json_path)
        self._add_output(json_path)
        map_path = os.path.join(self.output_dir, f"speaker_mapping_{run_ts}_tracks.json")
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(res.mapping, f, indent=2, ensure_ascii=False)
        self._add_output(map_path)
        txt = speaker_id.format_segments_to_text(res.segments, res.mapping, ignored_ids)
        txt_path = os.path.join(self.output_dir, f"transcript_{run_ts}_tracks.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt)
        self._add_output(txt_path)

        if self.session_id:
            try:
                self._persist_detected_speakers(self.session_id, res.segments, names=res.mapping)
            except Exception:  # noqa: BLE001 - review data is best-effort
                pass
        ... # then refine_speakers -> speakers_improvements_{ts}.json exactly as the Mixed branch does,
            # db.update_session(..., transcripts_folder, speakers_json_path, status="transcribed",
            #                   source_audio_files=json.dumps([t.path for t in tracks])),
            # voice stash: if res.embeddings and voice_match_enabled and session_id:
            #   voiceprints.stash_session_embeddings(self.session_id, res.embeddings)
        warning = multitrack.duration_mismatch(res.durations)
        # final status: warning (if any) prefixed to the usual "Done…" text
```

- **Shared blocks.** The improvements, session update and voice-stash blocks are the same as in the Mixed branch. Factor them into private helpers, `_write_improvements(all_segments, speakers_doc, provider)`, `_update_session_record(extra=None)` and `_stash_embeddings(emb)`, and call them from both branches rather than copying them. The Mixed branch's behavior must be byte-for-byte the same.
- **Session audio files.** Check how `source_audio_files` is stored in `app/data/db.py`, as a JSON text column, and how `db.update_session` accepts it. Use the same form that `load_session` reads back.
- **`_persist_detected_speakers` gains `names=None`.** With names, each new row's `display_name` is `names.get(lab, "")`. Mixed-mode calls stay unchanged.
- **The cancelled-row marking above is illustrative.** Use whatever row-state accessor the tab already has. Rows that never reached "complete" become failed with the detail "cancelled".

- [ ] **Step 4: Run the tests, then the CI-condition check**

Run: `.venv\Scripts\python -m pytest tests/gui/test_multitrack_run.py tests/gui/test_multitrack_tab.py tests/unit -q`

Then run the whole suite as CI sees it, with the fetched weights moved aside and the ML packages hidden. Restore the folder afterwards, even on failure:

```powershell
Rename-Item models models.ci-hidden
try { .venv\Scripts\python -c "import sys, pytest; [sys.modules.__setitem__(m, None) for m in ('whisperx','pyannote','torch','torchaudio','huggingface_hub')]; sys.exit(pytest.main(['-q','-p','no:cacheprovider','tests']))" } finally { Rename-Item models.ci-hidden models }
```

Expected: everything passes, with the existing single pyannote-metrics skip, and no hang.

- [ ] **Step 5: Full gate, commit**

```
git add app/ui/transcribe_tab.py tests/gui/test_multitrack_run.py
git commit -m "feat: multi-track run path — merged transcript, named speakers, no AI naming call"
```

---

## Manual check (controller, after Task 5)

Run multi-track mode from source on the two 60-minute tracks from the Discord spike, `Mike_….wav` and `Chip_….wav`, with model `small`. Use no session, or a throwaway one. Confirm:

1. One merged `transcript_*_tracks.txt` is produced, labelled `Mike:` and `Chip:` in time order.
2. No duration warning appears, since both tracks are 3600.81 seconds.
3. GPU is used.
4. The run time is roughly the sum of the speech in both tracks.
