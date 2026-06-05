# Voiceprint feasibility spike — DECISION (2026-06-05)

**Result: APPROACH A confirmed.** Per-speaker voice embeddings are available from the diarization pass at no extra cost. Proceed with Task 3.

## What the spike found (real audio: `H:\CS Test Audio\testaudio.wav`, device=cuda)
- The `return_embeddings=True` kwarg is **IGNORED** by the community-1 pipeline (`Ignoring unexpected keyword arguments: return_embeddings`). The old pyannote-3.1 `(diarization, embeddings)` tuple API is NOT available.
- **Instead**, `pyannote/speaker-diarization-community-1` returns a **`DiarizeOutput`** object with these public fields:
  - `.speaker_diarization` — `Annotation` (the diarization; `.labels()` = `SPEAKER_00…`).
  - `.exclusive_speaker_diarization` — `Annotation`.
  - `.speaker_embeddings` — `np.ndarray` shape **(num_speakers, 256)** — one **256-dim** centroid embedding per speaker, **row i ↔ `sorted(diarization.labels())[i]`**.
  - `.serialize` — method.
- So the per-cluster embeddings come from the SAME diarization pass (no extra model, no extra audio pass) — this IS approach A. **D = 256.**
- **Embedding quality (cross-speaker cosines, one clip, 9 detected speakers):** mostly **0.06–0.40**; one pair at **0.59** (SPEAKER_05 vs 06), almost certainly an over-split of one speaker (→ legitimately higher because it's the same voice). Different speakers are clearly distinguishable; same-person across sessions should score higher than these → the default **0.70** threshold is a reasonable conservative start (tunable via `voice_match_threshold`).

## Required recipe for Task 3 (extraction)
1. **Preload the audio as a waveform dict** — `torchcodec` is broken in this venv, so pyannote CANNOT decode a file path (`NameError: AudioDecoder is not defined`). Feed the pipeline an in-memory waveform (this is what whisperx's `DiarizationPipeline.__call__` already does). From the app's converted 16k-mono PCM wav:
   ```python
   import wave
   import numpy as np
   import torch
   with wave.open(wav16k_mono_path, "rb") as wf:
       sr, ch = wf.getframerate(), wf.getnchannels()
       raw = wf.readframes(wf.getnframes())
   a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
   if ch > 1:
       a = a.reshape(-1, ch).mean(axis=1)
   audio_input = {"waveform": torch.from_numpy(a[None, :]), "sample_rate": int(sr)}
   ```
2. **Reach the pyannote pipeline** inside whisperx's `DiarizationPipeline` (the transcriber builds `self._diarize = DiarizationPipeline(token=..., device=...)`): the inner pyannote pipeline is `self._diarize.model` (fallback `.pipeline`).
3. **Run once, take both** the diarization Annotation (for whisperx word-speaker assignment) AND the embeddings:
   ```python
   out = self._diarize.model(audio_input)        # DiarizeOutput
   diarization = out.speaker_diarization          # Annotation -> build the whisperx segments DataFrame from this
   labels = sorted(diarization.labels())
   embeddings = np.asarray(out.speaker_embeddings) # (len(labels), 256)
   per_cluster = {lab: embeddings[i].astype("float32") for i, lab in enumerate(labels)}
   ```
   For the transcript path, convert `diarization` (Annotation) → the segments DataFrame whisperx's `assign_word_speakers` expects (`itertracks(yield_label=True)` → rows of `start,end,speaker`), so it remains a SINGLE diarization pass that yields both the transcript labels and the fingerprint embeddings. Do NOT add a second diarization pass.
4. Do NOT touch GPU/device selection — the inner pipeline already lives on the pipeline's device.

## Notes
- Over-segmentation (9 "speakers" from one clip) is a diarization quality issue, not an embedding one; Spec 1's ① confirm-who's-here expected-speaker-count constrains it. The user maps/merges/ignores clusters in ② regardless.
- The throwaway `scripts/spike_embeddings.py` has been deleted (its working recipe is captured above).
