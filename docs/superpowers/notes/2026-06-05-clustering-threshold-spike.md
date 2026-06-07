# Clustering-threshold spike — RESULT: threshold knob is INERT (2026-06-06)

**Decision: do NOT build a clustering-threshold "voice separation" control (#51).** The
expected-voice-**count** constraint is the effective lever instead (#52).

## What was tested
`scripts/spike_clustering_threshold.py` on real audio (`H:\CS Test Audio\testaudiomultispeaker.wav`,
device=cuda). Loaded `pyannote/speaker-diarization-community-1` via whisperx's
`DiarizationPipeline`, reached the inner pipeline (`self._diarize.model`), and overrode
`pipe.clustering.threshold` across the VBx declared range, re-running diarization each time.

## Findings
- `clustering` is `VBxClustering`; the pretrained `threshold` reads **0.6**. The override
  attribute path (`pipe.clustering.threshold`) is settable.
- Speaker count vs threshold:
  - `None` (untouched pretrained) → **8 speakers**
  - `0.55` → 7 · `0.65` → 7 · `0.75` → 7
- **The threshold value does not steer the result.** Across the entire 0.55–0.75 sweep
  (the full "split more" → "merge more" intent) the count is flat at 7. Setting the
  attribute at all perturbs the run (8→7), but the *value* is inert — community-1's VBx
  variational refinement converges on its own count regardless of the AHC threshold seed.
- Going outside 0.5–0.8 is unsupported (VBx declared search range), so there is no usable
  monotonic knob here.

## Consequence
A `Merge↔Split` slider on this parameter would not do what its label promises — worse than
no control. **#51 deferred** (the threshold approach failed; a future experiment could probe
VBx `Fa`/`Fb` acoustic factors, but those are opaque and unpredictable for a DM, and are not
worth it unless the count control proves insufficient).

## What works instead
`min_speakers` / `max_speakers` (passed to the pipeline) DO constrain the result — already
used in the codebase. The split/merge *intent* is expressible through the count: to separate
two merged people, raise the expected count so the count window forces the extra cluster.
This is the basis for the count-only revision of the design (#52).
