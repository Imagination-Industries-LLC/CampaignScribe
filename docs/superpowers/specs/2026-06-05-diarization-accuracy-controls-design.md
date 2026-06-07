# Diarization Accuracy Controls — Design (count-only, post-spike)

- **Status:** Designed (brainstorm 2026-06-05); **revised 2026-06-06 after the spike** — scope cut to the expected-voice-count lever only. Ready to build (no remaining gate).
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/diarization-accuracy-controls`.
- **Builds on:** Spec 1 (Campaign Home redesign — the session flow's ① "Confirm who's here" step) and Spec 2 (Voice Auto-Match, single-pass diarization). Touches `app/core/transcriber.py` diarization, `app/ui/session_view.py` (① step), `app/ui/app_window.py`, `app/ui/transcribe_tab.py`.
- **Planning issues:** private board #52 (prominent expected-voice count) — **built here**. Board #51 (clustering sensitivity) — **deferred**: the spike proved the community-1 VBx `clustering.threshold` is inert (see below).

## What the spike changed
The original design had two levers: a Merge↔Split clustering-threshold control (#51) and the expected-voice count (#52). The Task 0 spike (`docs/superpowers/notes/2026-06-05-clustering-threshold-spike.md`) found community-1's VBx clustering **ignores the threshold value** — sweeping it across the full 0.55–0.75 range produced an identical speaker count. A separation slider on that parameter would not do what its label promises, so **#51 is dropped from this build and deferred.**

The same investigation confirmed the **speaker-count constraint** (`min_speakers`/`max_speakers`, already honored by the pipeline) is the reliable lever — and that the split/merge *intent* is expressible through it: to separate two merged people, the DM raises the expected count and the count window forces the extra cluster. So this design ships a **single, strong expected-voice-count control**, which subsumes what the separation slider was trying to do.

## Problem
Real-world use surfaced under-segmentation: a speaker was **missed** (merged into another), and in a later session two people were **merged into one**. The session ① "Confirm who's here" step already derives `expected_speaker_count()` (roster + guests − absent), but the transcribe pass **ignores it** — it reads the Transcribe tab's own spinbox, seeded from a static `default_num_speakers = 5`. The accurate, roster-derived number never reaches diarization, so the app has no usable way to say "find the voice you missed."

## What this adds
One per-session lever in the ① step: the **expected-voice count**, made prominent (an editable field, pre-seeded from the roster) and **wired to the run** as the diarization speaker-count constraint.

## Locked decisions
1. **Scope: per-session, in the ① step.** The count is editable in ① and pre-seeds from `expected_speaker_count()`. No global setting is needed (the count is inherently per-session); `default_num_speakers` remains the loose-file fallback only.
2. **Binding: "at least N, room for one more."** `min_speakers = N`, `max_speakers = N+1` (clamped `min ≥ 1`). Revised from the original symmetric N±1: since the count is now the *sole* lever and the observed bug is *under*-counting, forcing **at least** the confirmed count directly pushes a missed voice out, while `+1` headroom allows one unlisted/surprise voice. The DM lowers the number if it ever over-splits (a present-but-silent person).
3. **Supersedes the static default-5 spinbox for session-driven runs.** The standalone Transcribe tab spinbox stays as the fallback for **loose-file (non-session) transcribes**, where its integer is passed as an exact count (`min=max=N`) — behavior intentionally unchanged.
4. **No persistence/schema changes.** The count is a pure input to diarization. The per-session value is threaded in-memory through the existing `open_session_stage → load_for_session` handoff; no DB columns, no migration.
5. **Best-effort / no-regression.** At "Normal" usage (DM leaves the pre-seeded count) the result is the roster-constrained diarization; nothing about the transcript/embedding path (Spec 2 single-pass) changes except the speaker-count window handed to the pipeline.

## Architecture / components

### `app/core/transcriber.py`
- New pure, Tk-free helpers (unit-tested in isolation):
  - `speaker_count_window(num_speakers=None, min_speakers=None, max_speakers=None) -> dict` — builds the diarization `min/max_speakers` kwargs. Explicit min/max win; otherwise `num_speakers` (>0) locks exact (`min=max=N`). Floors at 1. `{}` = unconstrained.
  - `diarization_run_kwargs(expected_count, fallback_count) -> dict` — the UI translation: `expected_count > 0` → `{min_speakers: max(1, N), max_speakers: N+1}`; else `{num_speakers: fallback_count}` (loose-file exact).
- `transcribe_file(...)` changes its count interface so the **caller** owns the window: accept explicit `min_speakers`/`max_speakers` (plus a back-compat `num_speakers` that maps to `min=max=N`), replacing the internal `min=max=num_speakers` exact-lock. The single-pass `return_embeddings=True` diarization call (Spec 2) is otherwise unchanged.

### `app/ui/session_view.py` (① "Confirm who's here")
- Replace the read-only "Expected voices: N" label with a clearly-labeled **editable spinbox**, pre-seeded from `expected_speaker_count()` and kept in sync as present/absent toggles change. This is the value the run uses, so it is prominent and hard to skip.
- On "Start transcription ▸", thread the count to the run via the handoff (below).

### `app/ui/app_window.py` + `app/ui/transcribe_tab.py`
- `open_session_stage(session_id, stage, run_params=None)` forwards `run_params` to `load_for_session(session, run_params=None)`.
- `TranscribeTab` stores `self._run_params` and, in `_worker`, derives the diarization kwargs via `transcriber.diarization_run_kwargs(run_params.get("expected_count"), self.spk_var.get())`. Session-driven → soft "at least N" window; loose-file / direct navigation → exact spinbox. `_run_params` resets on a plain `load_session` so a manual reopen doesn't reuse stale ① values.

## Data flow (one session, session-driven)
1. ① "Confirm who's here": the editable count pre-seeds from roster+guests−absent.
2. DM starts the transcribe → SessionView passes `{expected_count: N}` through `open_session_stage`.
3. `transcribe_file` runs the single diarization pass with `min_speakers=N, max_speakers=N+1`.
4. Diarization, constrained toward the confirmed count, yields fewer missed/merged voices → flows into ② Review (and Spec 2 voice pre-fill) unchanged.

## Out of scope (deferred)
- **Clustering sensitivity / separation control (#51)** — threshold inert per spike; deferred. A future experiment could probe VBx `Fa`/`Fb`, only if the count control proves insufficient.
- Per-campaign persisted count.
- Auto-suggesting a count nudge from detected-vs-expected mismatch ("found 6, you expected 8 — re-run?").
- Re-running diarization from ② without re-transcribing (separate perf item).

## Risks & mitigations
- **Count too high (present-but-silent person) → over-split phantom speaker.** The DM controls the number and confirms presence in ①; the `+1`-only headroom limits inflation; lowering the count is the immediate fix. ② Review lets the DM ignore a stray cluster regardless.
- **Multi-file sessions:** the count applies per `transcribe_file` call (per audio file), same as today; no change to multi-track handling.
- **No regression for loose files:** that path keeps exact `num_speakers` behavior unchanged.

## Test plan
- **Unit (Tk-free, Linux lane):** `speaker_count_window` (exact from num_speakers, explicit range wins, unconstrained empty, floor at 1) and `diarization_run_kwargs` ("at least N" window from expected_count, exact fallback, floor at 1).
- **GUI (`@pytest.mark.gui`, Windows lane):** ① renders the editable pre-seeded count field and exposes it for the run; `_start_transcription` hands the count to `open_session_stage` as `run_params`.
- **Manual (USER, after build):** on a session that previously merged two people, set the count to the true number and re-transcribe → the missed voice appears as its own cluster in ② Review; loose-file transcribe unchanged; transcript + Spec 2 pre-fill still work.
