# Voice Auto-Match — Design (Spec 2 of the Campaign Home redesign)

- **Status:** Designed (brainstorm 2026-06-04), not yet implemented
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/voice-auto-match`.
- **Builds on:** Spec 1 (Campaign Home & Session redesign, merged PR #23). Reuses the session flow's **② Review Speakers** step, the per-session `speaker_profiles` mapping, `app/core/library.py` campaigns, and `app/core/transcriber.py` diarization.
- **Planning issue:** private board #7.

## Problem
After Spec 1, the session flow's **② Review Speakers** is **manual**: for each detected diarization cluster (`SPEAKER_00`, …) the DM picks the matching roster member from a dropdown, every session. Diarization labels are not stable across recordings, so there's no carry-over — the same people get re-assigned by hand each time. The redesign's "stable roster = near-zero-touch" promise depends on recognizing the **same human voice across sessions**, which the app cannot do today.

## What this adds
A **voice fingerprint** per roster member, learned from the DM's own ② confirmations, used to **pre-fill** ② in future sessions. The system gets smarter every session with no separate enrollment step.

## Locked decisions (brainstorm 2026-06-04)
1. **Learn from confirmations** — no separate enrollment screen. When the DM confirms a detected cluster = a roster person in ② (or saves a Discover-seeded roster), the app captures that cluster's voice embedding into that person's fingerprint. Fingerprints accumulate across sessions.
2. **Pre-fill + confirm** — ② still always shows; each detected cluster comes **pre-assigned** to its matched roster member with a confidence indicator, unmatched/low-confidence clusters flagged. The DM glances + confirms or overrides. A fully-recognized roster is a one-glance confirm (keeps the review checkpoint; no silent auto-apply).
3. **Embedding extraction** is new work; the plan **opens with a feasibility spike**. Preferred approach **A** (pyannote `return_embeddings`); fallback **B** (separate embedding pass). See below.
4. **Separate per-campaign fingerprint store** — NOT inside the versioned `speakers.json` (embeddings are mutable + accumulating; keep them out of the immutable version files and out of the JSON doc).
5. **Running-mean centroid per person** (+ a sample count), updated incrementally on confirmation. Simple, compact, self-correcting. Multiple-embeddings-per-person is a deferred v2 refinement.
6. **Capture only on user-confirmed assignments** — never from unconfirmed Claude/Discover guesses, so wrong fingerprints aren't learned.
7. **Privacy:** embeddings are biometric-adjacent → stored **locally only**, per campaign; PRIVACY.md gains a line.

## Architecture (4 parts)
1. **Embedding extraction** (`app/core/transcriber.py` + a small helper): during a session's diarization pass, produce **one embedding vector per detected speaker cluster** (a centroid of that cluster's speech).
2. **Fingerprint store** (`app/core/voiceprints.py`, Tk-free): per-campaign, per-person voice fingerprints — load/save, `update(person, embedding)` (incremental running mean), `match(cluster_embeddings) -> {cluster: (person, score)}`.
3. **Matcher** (in `voiceprints.py`): cosine similarity of this session's cluster embeddings vs the campaign's roster fingerprints; returns the best person + score per cluster; "no match above threshold" → unknown.
4. **② integration + learning loop** (`app/ui/session_view.py`): pre-fill the ② assignment dropdowns from the matcher; on confirm/override (`_save_session_mapping`), feed each confirmed (cluster embedding → person) back into the store via `update(...)`.

## The embedding-extraction fork (spike resolves)
- **A — pyannote `return_embeddings` (preferred):** call the community-1 `SpeakerDiarization` pipeline directly with `return_embeddings=True`, yielding per-speaker **centroid embeddings in the same diarization pass** — no extra model load, no extra audio pass. Requires running diarization via pyannote directly (around whisperx's `DiarizationPipeline` wrapper) for the embedding-bearing path, or accessing the wrapped pipeline. Must verify community-1 supports `return_embeddings` and that whisperx word-assignment still works from the same diarization result.
- **B — separate embedding pass (fallback):** keep whisperx diarization as-is; after it, run a dedicated embedding model (`pyannote/embedding` or a wespeaker model) via `pyannote.audio.Inference`, crop to each speaker's merged segments, average → fingerprint. Decoupled + robust, but an extra model + extra pass (slower) and possibly another HF model license.
- **Spike (plan Task 0):** on a real multi-speaker clip, extract per-speaker embeddings via A; confirm two recordings of the same person score a high cosine similarity vs a low one cross-person. Pick A or B based on the result. **No further Spec-2 work proceeds until the spike passes.**

## Data model
- **Fingerprint store** — one numpy `.npz` file per campaign under the library folder: `%APPDATA%\CampaignScribe\library\<slug>\fingerprints.npz` (compact for float32 vectors; loaded with `numpy.load`). A sidecar `fingerprints.json` holds the per-person `count`/`updated_at` metadata if cleaner than packing it into the npz. Schema (conceptually):
  ```
  { person_key: { "centroid": float32[D], "count": int, "updated_at": iso } }
  ```
  `person_key` = the roster person's display name within the campaign (v1). Rename-reassociation is a known edge case (deferred — a rename would orphan the old key; acceptable for v1, the next confirmation re-learns).
- **Embedding dimensionality** D is whatever the chosen model emits (e.g. 192/256/512); the store is agnostic.
- **Session clusters** keep using the existing per-session `speaker_profiles` rows (Spec 1); Spec 2 additionally needs the per-cluster embedding at ② time — passed in-memory from the extraction step to the matcher to the ② view (NOT persisted to the DB; only the resulting confirmed fingerprints persist to the store).
- **Config:** `voice_match_threshold` (default ~0.70, tunable), `voice_match_enabled` (default true). In `DEFAULT_CONFIG`.

## Data flow (one session)
1. Session runs diarization (Transcribe stage / identify) → detected clusters + **per-cluster embeddings** (extraction).
2. `voiceprints.match(campaign_slug, cluster_embeddings)` → `{cluster: (person, score)}` using the campaign's stored fingerprints.
3. ② Review opens **pre-filled**: each cluster's dropdown set to its matched person when `score ≥ threshold` (with a confidence chip); below-threshold/no-match clusters flagged unknown.
4. DM confirms/overrides → `_save_session_mapping` writes the session-local mapping (Spec 1) AND calls `voiceprints.update(campaign_slug, person, cluster_embedding)` for each confirmed cluster → the person's centroid is incrementally updated.
5. Next session: step 2 now recognizes returning voices → ② is pre-filled/all-green.

## UX (mostly the existing ② screen, enhanced)
- Each detected-cluster row in ② gains a **confidence chip** (e.g. "Mike · 0.83" or "⚠ no match"). High-confidence rows are pre-selected; the DM can override any.
- An **override** (the DM changes a pre-filled match) is treated as a correction: it updates the *chosen* person's fingerprint, not the wrongly-suggested one.
- Edit Profile (optional, low priority): show a small "voice learned ✓ (N samples)" indicator per roster member; a "forget voice" action to reset a polluted fingerprint. (Nice-to-have; can defer.)

## Components / files
- **New `app/core/voiceprints.py`** (Tk-free): the store + matcher + incremental update. Pure-numpy; no Tk.
- **Modify `app/core/transcriber.py`**: expose per-cluster embeddings from the diarization pass (approach A or B).
- **Modify `app/ui/session_view.py`**: pre-fill ② from `voiceprints.match(...)`; on save, call `voiceprints.update(...)`. Pass cluster embeddings from the run into the view.
- **Modify `app/config.py`**: `voice_match_threshold`, `voice_match_enabled`.
- **Modify `PRIVACY.md`** + the in-app Privacy dialog text: note local-only voice fingerprints.
- **Tests:** `tests/unit/test_voiceprints.py` (Tk-free — synthetic vectors: update/running-mean, match/threshold, no-match, persistence round-trip); a `@pytest.mark.gui` test that ② pre-fills from a stubbed matcher; the spike is a manual/throwaway validation (not a committed test).

## Out of scope (deferred)
- Multiple embeddings per person / clustering of a person's voice modes (v2 robustness).
- Cross-campaign voice matching (fingerprints are per-campaign).
- Stable per-person IDs to survive renames (v1 keys by display name).
- Auto-skip ② entirely when fully confident (decision 2 keeps the checkpoint).
- Speaker verification/anti-spoofing, voice-based security.

## Risks & mitigations
- **Embedding extraction feasibility** (the big one) → **spike first**; A-preferred / B-fallback; do not build the rest until the spike passes.
- **Fingerprint pollution** from a wrong confirmation → mitigated by pre-fill+**confirm** (the DM reviews every session) and the running-mean (one bad sample is diluted); plus a future "forget voice" reset.
- **Threshold tuning** (false matches vs misses) → configurable; conservative default; below-threshold always falls to manual.
- **Privacy/biometric** concern → local-only storage, documented; no upload.
- **Perf** → approach A adds ~no cost (same diarization pass); B adds an embedding pass — a reason to prefer A.

## Test plan
- **Unit (Tk-free, Linux lane):** `voiceprints` store — incremental running-mean correctness, cosine match picks the right person, threshold gating, no-match path, npz/json persistence round-trip, rename-orphan behavior is graceful (no crash).
- **GUI (`@pytest.mark.gui`, Windows lane):** ② pre-fills assignments from a stubbed/in-memory matcher; an override updates the chosen person; a fully-recognized set shows all-confident.
- **Spike (manual):** same-person-high / cross-person-low cosine on a real clip — gates the whole feature.
