# CampaignScribe

Windows desktop app that transcribes D&D session audio with WhisperX +
pyannote diarization, identifies who said what against a `speakers.json`
profile, and generates per-part and consolidated session summaries with the
Anthropic Claude API.

This bundle was built from the project design spec and the reference scripts
(`transcribe.py`, `format_transcript.py`, `session_summary_prompt.txt`,
`speakers.json`) in the `CampaignScribe reference docs` folder.

## Tabs

1. **Discover** — drop a sample recording, run WhisperX + diarization, ask
   Claude to suggest initial speaker profiles, save to local SQLite.
2. **Refine** — analyze new audio against an existing `speakers.json` and
   review per-suggestion accept/reject improvements (also accepts the
   `speakers_improvements_*.json` files Tab 5 produces).
3. **Build Profile** — name speakers, assign character/role, mark
   include/exclude, write a fresh `speakers.json`.
4. **History** — browse all sessions in the database, rename, open files,
   delete records (files on disk are never deleted).
5. **Transcribe** — full pipeline against one or more audio files with a
   chosen `speakers.json`. Produces `transcript_N.json/.txt`,
   `speaker_mapping_N.json`, and a `speakers_improvements_*.json` review file.
6. **Summarize** — per-transcript summaries with the default D&D session
   prompt (or any custom user prompt), plus optional consolidation into a
   thematically-named `.docx` session summary.

## Prerequisites

- Windows 10 / 11
- For the bundled .exe: nothing — Python and the full PyTorch + CUDA runtime
  are included by PyInstaller.
- **GPU acceleration**: this build bundles `torch 2.11+cu128` (CUDA 12.8 runtime).
  CUDA is forward-compatible at the driver level, so any NVIDIA driver
  supporting CUDA 12.8 or newer (driver 525.x or newer on Windows) will let
  the app use the GPU. If no compatible GPU/driver is found, the app falls
  back to CPU automatically and the status bar explains why.
- An [Anthropic API key](https://console.anthropic.com/settings/keys).
- A [HuggingFace token](https://huggingface.co/settings/tokens) AND license
  acceptance for the diarization model used by whisperx 3.8+ (one click):
  - https://huggingface.co/pyannote/speaker-diarization-community-1

  If you have not accepted the license, the app will fail with an opaque
  pyannote error. Tabs 1 and 5 now check for a HF token before starting and
  point you here if it's missing.

### GPU status messages

The bottom-of-window status bar reports one of:

- 🟢 **GPU: \<name\> (\<vram\>GB) — Transcription ready** — CUDA torch found a
  compatible GPU and will use it.
- 🟡 **GPU detected but PyTorch can't use it — falling back to CPU** — an
  NVIDIA GPU is present (`nvidia-smi` sees it) but `torch.cuda.is_available()`
  returns False. Usually means the NVIDIA driver is too old. Update from
  https://www.nvidia.com/Download/index.aspx or install the CUDA toolkit:
  https://developer.nvidia.com/cuda-downloads
- 🟡 **No NVIDIA GPU detected — CPU mode** — no NVIDIA hardware. Transcription
  will work but is very slow on multi-hour sessions.
- 🔴 **PyTorch not available** — the bundle is broken; reinstall.

## Running

Double-click `CampaignScribe.exe`. On first run:

1. The app creates `%APPDATA%\CampaignScribe\` for its database and config.
2. A banner reminds you to add API keys via the gear icon (top right).
3. The status bar shows GPU detection — green = CUDA, yellow = CPU only.

Recommended workflow for a brand-new campaign:

1. Tab 1: feed in a 30–60 minute sample, get baseline speaker profiles.
2. Tab 3: name each speaker, write a `speakers.json`.
3. Tab 5: run the full session(s) using that `speakers.json`.
4. Tab 6: summarize each transcript and consolidate into one session doc.
5. Tab 2 (later): refine `speakers.json` from new sessions.
6. Tab 4: history of every session.

## Running from source

```cmd
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

The shipped bundle uses CUDA 12.8 torch. If you want a different CUDA
version (or CPU-only), install torch first with the matching wheel index:

```cmd
:: CUDA 12.8 (default, matches the shipped bundle)
.venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

:: CPU-only (smaller bundle, no GPU)
.venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

.venv\Scripts\pip install -r requirements.txt
```

## Building the .exe

```cmd
build.bat
```

Output lands in `dist\CampaignScribe\` (folder bundle — keep all files
together; the .exe will not work alone). The CUDA build is ~4–5 GB because
it bundles CUDA + cuDNN + cuBLAS DLLs alongside `torch`, `whisperx`,
`pyannote`, and `ffmpeg.exe`.

## Storage

- App data: `%APPDATA%\CampaignScribe\data.db`, `config.json`
- API key + HF token: Windows Credential Manager (via `keyring`), never on
  disk.
- Audio files, transcripts, summaries: wherever you point the output folder.

## Troubleshooting

- **"PyTorch not available" in status bar** — you launched a build with no
  bundled torch, or a CUDA build on a machine without a matching driver.
  Re-run `build.bat` from a clean venv.
- **HuggingFace 403 / cannot download diarization model** — accept the
  license on both pyannote model pages and verify your HF token is set in
  Settings.
- **Claude 401** — the API key in Settings was rejected; re-paste it.
- **CUDA out of memory** — try a smaller Whisper model (medium / small).
