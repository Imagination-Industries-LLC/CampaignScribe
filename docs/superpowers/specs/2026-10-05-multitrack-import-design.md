# Multi-Track Import (Phase 4a) — Design

- **Feature:** Phase 4, part a, of #4 Discord Voice Recording (planning issue CampaignScribe-planning#13)
- **Date:** 2026-10-05
- **Context:** The May 2026 Discord spec's py-cord approach no longer works, because Discord's DAVE voice encryption is mandatory for bots since 2026-03. The work is split in two:
  - **4a (this spec):** multi-track import. It has no Discord dependency.
  - **4b (later spec):** a live recording bot, run as a Node.js helper process.
- **Spike for 4b:** a 60-minute soak on 2026-10-05 recorded per-user tracks that were time-aligned to the sample, with flat memory and no dropouts. 4b will write one file per person into exactly the pipeline this spec builds.

## Problem

Today CampaignScribe works on one mixed recording, and pyannote guesses who is speaking. Some recorders already capture one file per person: the Discord bot in 4b, Craig, and per-player mics. When every file is one person, speaker detection is unnecessary and the labels are certain. There is no way to feed such files in today.

## Goals

1. Transcribe a set of per-speaker audio files into **one** speaker-labeled transcript, with no speaker detection.
2. Let the user name each track. Names are pre-filled from the filenames and can come from the campaign's players.
3. Per track, optionally run speaker detection when several people shared one mic.
4. Produce the same outputs, session state and downstream behavior as today, so Summarize, Review and Refine work unchanged.

## Non-goals (v1)

- Per-track time offsets. All tracks are assumed to start at the same moment, as Craig and the 4b recorder produce them. Mismatched lengths only trigger a warning.
- Removing speech that leaks into another person's mic.
- Training voiceprints from the tracks.
- Remembering the per-session file-to-name mapping. Re-running pre-fills the names from the filenames again.
- The live Discord bot (4b).

## Design

### 1. Core module — new `app/core/multitrack.py` (Tk-free)

```python
@dataclass(frozen=True)
class Track:
    path: str
    speaker: str          # display name, e.g. "Mike"
    shared_mic: bool = False

def name_from_filename(path: str) -> str:
    """Best-guess speaker name from a per-speaker file name."""

def track_label(index: int) -> str:
    """Stable speaker id for a track: TRACK_01, TRACK_02, ..."""

def merge_segments(per_track: list[list[dict]]) -> list[dict]:
    """All tracks' segments in one list sorted by (start, track order); stable."""

def duration_mismatch(durations: dict[str, float], tolerance_s: float = 2.0) -> str:
    """'' when all durations agree within tolerance; else a one-line warning naming the shortest and longest file."""
```

`name_from_filename` handles three formats, falling back to the bare file stem:
- **Craig:** `1-mike_1234.flac` gives `mike`. Strip the leading `<n>-` and the trailing `_<digits>`.
- **The 4b recorder:** `Mike_1083839469700001892.wav` gives `Mike`. Strip a trailing `_<15+ digits>`.
- **Plain:** `Sarah.m4a` gives `Sarah`.

Any other stem is returned as-is, with underscores turned into spaces and surrounding whitespace trimmed.

**Segments.** Each track's segments carry `speaker = track_label(i)`. A shared-mic track instead carries `f"{track_label(i)}_{pyannote_label}"`, for example `TRACK_02_SPEAKER_00`. The keys stay exactly `start, end, text, speaker`, the same shape `transcribe_file` returns.

**Speaker mapping.**
- Each plain track maps `{TRACK_0n: <track speaker name>}`.
- Each shared-mic sub-speaker maps to `"<name> (1)"`, `"<name> (2)"` and so on, in order of first appearance. The user renames them in Review as today.

### 2. Pipeline — `app/core/transcriber.py`

Add a method alongside `transcribe_file`:

```python
def transcribe_track(self, wav_path, *, diarize=False, num_speakers=None,
                     min_speakers=None, max_speakers=None, progress=None) -> list[dict]:
```

- It runs the same load, Whisper, alignment and output-shaping steps as `transcribe_file`.
- With `diarize=False`, it skips pyannote and labels every segment `"SPEAKER_00"`. The caller relabels.
- With `diarize=True`, it runs the existing diarization step unchanged, including the speaker-count kwargs and the embeddings fallback.
- Models load once and are reused across tracks: the existing lazy `_load_models` cache and the alignment-model cache.
- The shared steps are factored into private helpers, so `transcribe_file` and `transcribe_track` don't duplicate logic. The behavior and return shape of `transcribe_file` are unchanged.
- `_last_speaker_embeddings` is reset at the start of each `transcribe_track` call. It is set only by a diarized track.

### 3. Orchestration — `multitrack.transcribe_tracks`

```python
def transcribe_tracks(pipeline, tracks: list[Track], *, wav_for, shared_mic_count_kwargs,
                      progress=None) -> tuple[list[dict], dict[str, str]]:
    """Transcribe every track, relabel, merge. Returns (merged_segments, mapping)."""
```

- `wav_for(track) -> str` converts a track and returns a temporary WAV path. The tab passes `audio.convert_to_wav`, and the function deletes each temp file after its track.
- `shared_mic_count_kwargs` is the speaker-count kwargs for diarized tracks. The tab computes it with the existing `diarization_run_kwargs`.
- `progress(track_index, stage, fraction)` reports progress. It may raise `InterruptedError` to cancel, which is checked between tracks and stages.
- Tracks run sequentially, in the user's order.

### 4. UI — `app/ui/transcribe_tab.py`

**A mode switch** sits above the audio-file area, as two radio buttons:
- **Mixed recording** is the default and today's behavior.
- **One file per speaker** is the new mode.

**In "One file per speaker" mode:**
- **Track table.** The file listbox is replaced by a `ttk.Treeview` track table with three columns:
  - **File:** the base name.
  - **Speaker:** the name.
  - **Shared mic:** ☐ or ☑.
- **Adding files.** The same Add Files…, Remove Selected and Clear All buttons apply. Adding files pre-fills **Speaker** with `name_from_filename`.
- **Editing a track.** Double-clicking a row, or selecting it and clicking **Edit track…**, opens a small inline editor. It has a combobox of the active campaign's player names plus free text, and a Shared mic checkbox.
- **Speaker count.** The "# speakers" spinbox is relabelled "# speakers per shared mic" and enabled only when a track is marked shared.
- **Output.** The progress tree shows one row per track. The output list shows the combined outputs.

**Switching modes** keeps the chosen files. A session loaded from the session list always opens in Mixed mode, as today.

### 5. Run flow (tab worker, multi-track mode)

**Pre-flights** are the same as Mixed mode, in the same order: speakers profile, files, AI provider, model files, output folder. Two checks are added:
- **At least 2 tracks.** With fewer: "Add at least two files (one per speaker), or switch to Mixed recording."
- **Every track named.** No blank speaker names: "Give every track a speaker name."
- **Duration check.** Each file's duration is read with ffmpeg probe in the worker. If `duration_mismatch` returns a warning, it appears in the status line, and the run continues.

**Processing:**
1. Build `TranscriptionPipeline(model_size=...)` and call `transcribe_tracks(...)`.
2. Write the outputs into the output folder, using `run_ts`:
   - `transcript_{run_ts}_tracks.json`, the merged segments.
   - `speaker_mapping_{run_ts}_tracks.json`, the mapping.
   - `transcript_{run_ts}_tracks.txt`, written with `speaker_id.format_segments_to_text(merged, mapping, ignored_ids)`.
3. **Skip** `speaker_id.identify_speakers`. The mapping is already known, so no AI call is made for naming.
4. Persist speakers when a session is selected. For each mapping key, add a `speaker_profiles` row with `source_speaker_id = key`, `display_name = mapping[key]`, and `include_in_tracking = 1`. Set `num_speakers_detected = len(mapping)`.
5. When the run was not cancelled, run `speaker_id.refine_speakers(merged, speakers_doc, provider)` and write `speakers_improvements_{ts}.json`, as today.
6. If a session is selected, call `db.update_session(... transcripts_folder, speakers_json_path, status="transcribed")`, as today. `source_audio_files` is set to the track paths.
7. **Voice match stash.** Only when exactly one track was diarized, stash that track's embeddings. The cluster labels are rewritten to their `TRACK_0n_SPEAKER_xx` ids. Otherwise nothing is stashed.

**Error handling:**
- A failing track marks its row failed, logs via `config.log_exception`, and the run continues with the remaining tracks. The merged transcript notes nothing about the gap. The failure stays visible in the tree.
- If every track fails, no outputs are written.
- Cancel stops after the current stage, leaves completed outputs unwritten, and marks the remaining rows cancelled.

## Testing

- **Unit, `tests/unit/test_multitrack.py`:**
  - `name_from_filename` for Craig, 4b-recorder and plain names, plus odd stems.
  - `track_label`.
  - `merge_segments` ordering, including a tie broken by track order and empty tracks.
  - `duration_mismatch` within and over tolerance.
  - `transcribe_tracks` with a fake pipeline checks:
    - relabelling and the mapping, including shared-mic sub-speakers;
    - temp-file deletion;
    - `InterruptedError` propagating;
    - a failing track not stopping the others, as reported back.
- **Unit, transcriber:** `transcribe_track(diarize=False)` never calls the diarization model and labels `SPEAKER_00`. `transcribe_track(diarize=True)` matches `transcribe_file`. `transcribe_file`'s existing tests still pass. All of this uses the existing `sys.modules` whisperx fakes.
- **GUI, `tests/gui/test_multitrack_tab.py`:**
  - the mode switch shows the track table;
  - adding files pre-fills names;
  - the edit dialog changes the name and shared mic;
  - each pre-flight message;
  - a run with a fake pipeline writes the three outputs, persists speaker rows with names, sets the session to transcribed, and makes no `identify_speakers` call.
- **CI rules:** no real model files, ML packages, or blocking modal dialogs, as with the existing GUI tests.
- **Manual check:** the two 60-minute tracks from the 4b spike (`Mike_…wav` and `Chip_…wav`) produce one merged transcript, with both names correct and ordered by time.
