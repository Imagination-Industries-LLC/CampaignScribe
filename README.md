# CampaignScribe

Windows desktop app that transcribes tabletop RPG session audio with WhisperX +
pyannote diarization, works out who said what against a campaign's speaker
roster, and generates per-part and consolidated session summaries with the
Anthropic Claude API.

Campaigns own their sessions and a versioned speaker roster. The app learns
each player's voice across sessions and pre-fills speaker review for you.

## Layout

The window has four tabs plus a menu bar.

1. **Home** — the campaign + session hub. Pick or create a campaign, import an
   existing `speakers.json`, open **Edit profile** (the campaign-scoped,
   auto-versioned roster editor), and manage the campaign's sessions (new,
   open, rename, delete record). A session opens in its own window with a
   three-step flow: add audio tracks → **① Confirm who's here** (set the
   expected voices for this run, add guests) → **Start transcription** →
   **② Review speakers** (voice auto-match pre-fills the mapping; fix anything
   wrong and **Save changes to profile**).
2. **Transcribe** — the full pipeline (WhisperX + diarization + Claude speaker
   ID) against one or more audio files for a chosen campaign. Produces
   `transcript_N.json/.txt`, `speaker_mapping_N.json`, and a
   `speakers_improvements_*.json` review file. Starting on a campaign with no
   roster yet offers **Discover**: run a lighter model over the first file,
   let Claude propose initial speaker profiles, then review them in Edit
   profile.
3. **Summarize** — per-transcript summaries with the default D&D session
   prompt (or any custom prompt), plus optional consolidation into a
   thematically named `.docx` session summary.
4. **Refine** — analyze new audio against the campaign's current roster and
   accept/reject per-speaker improvements. Accepting appends a new roster
   version (history is never overwritten).

Menu bar:

- **File** → Settings (AI provider, model and API key — Claude, Google
  Gemini, OpenRouter, a local Ollama / LM Studio model, or a custom
  OpenAI-compatible endpoint — plus HuggingFace token, default and
  discovery Whisper models, output folder, expected speakers, theme,
  voice-match threshold, crash reporting opt-in) · Exit
- **Tools** → Open Logs Folder · Open Data Folder
- **Help** → Getting Started · Privacy & Data (see [PRIVACY.md](PRIVACY.md)) ·
  Feedback & Support (scrubbed diagnostics bundle, report a problem, email,
  GitHub Discussions, Ko-fi) · About

Theme follows the OS by default and can be forced to dark or light in Settings.

## Prerequisites

- Windows 10 / 11
- Python 3.11 (`py -3.11`) when running from source. The packaged bundle
  includes Python and the full PyTorch + CUDA runtime.
- **GPU acceleration**: the pinned stack is `torch 2.11+cu128` (CUDA 12.8
  runtime). CUDA is forward-compatible at the driver level, so any NVIDIA
  driver supporting CUDA 12.8 or newer will let the app use the GPU. If no
  compatible GPU/driver is found, the app falls back to CPU automatically and
  the status bar explains why.
- An API key for the AI provider you choose in Settings → AI model:
  [Anthropic](https://console.anthropic.com/settings/keys) (default),
  [Google Gemini](https://aistudio.google.com/apikey), or
  [OpenRouter](https://openrouter.ai/keys). A custom OpenAI-compatible
  endpoint (for example a local Ollama server) needs a base URL and model
  instead; a key is optional there. To run with no API cost and no data
  leaving your PC, install [Ollama](https://ollama.com) (or LM Studio),
  pull a model such as `ollama pull qwen2.5:14b`, and pick **Ollama
  (local)** in Settings → AI model; **Detect** lists the models you have
  installed. Models of 12B parameters and up give the best results for
  speaker identification.
- A [HuggingFace token](https://huggingface.co/settings/tokens) AND license
  acceptance for the diarization model (one click):
  - https://huggingface.co/pyannote/speaker-diarization-community-1

  Without the license click pyannote fails with an opaque error. Transcribe
  and Discover check for a token before starting and point you here if it is
  missing.

### GPU status messages

The bottom-of-window status bar reports one of:

- 🟢 **GPU: \<name\> (\<vram\>GB) — Transcription ready** — CUDA torch found a
  compatible GPU and will use it.
- 🟡 **GPU detected but PyTorch can't use it — falling back to CPU** — an
  NVIDIA GPU is present (`nvidia-smi` sees it) but `torch.cuda.is_available()`
  returns False. Usually the NVIDIA driver is too old. Update from
  https://www.nvidia.com/Download/index.aspx or install the CUDA toolkit:
  https://developer.nvidia.com/cuda-downloads
- 🟡 **No NVIDIA GPU detected — CPU mode** — no NVIDIA hardware. Transcription
  works but is very slow on multi-hour sessions.
- 🔴 **PyTorch not available** — the environment is broken; re-run
  `setup_venv.bat` (or reinstall the bundle).

## Running from source (current dev loop)

```cmd
setup_venv.bat   :: once — creates .venv and installs the pinned ML stack
run_dev.bat      :: launch the app from source; edit code, save, relaunch
```

`setup_venv.bat` is a two-step install on purpose: whisperx 3.8.5 declares a
stale `torch~=2.8.0` + `torchvision` dependency, so the script installs the
app deps first, removes torchvision, then force-reinstalls `torch`/`torchaudio`
`2.11.0+cu128`. Do **not** `pip install -r requirements.txt` directly into a
fresh venv; see the comments in `setup_venv.bat` and `requirements.txt`.

First run:

1. The app creates `%APPDATA%\CampaignScribe\` for its database, config,
   speaker library and logs.
2. A banner reminds you to add the API key for your chosen AI provider via
   **⚙ Settings**.
3. The status bar shows GPU detection — green = CUDA, yellow = CPU only.

Recommended workflow for a brand-new campaign:

1. **Home** → ＋ New campaign.
2. **Home** → ＋ New session → add the recording → ① confirm who's here →
   start transcription. With no roster yet, accept the Discover prompt and
   review the proposed speakers in Edit profile.
3. ② Review speakers → save changes to the profile.
4. **Summarize** the transcript(s) and consolidate into one session doc.
5. Later sessions: voice auto-match pre-fills ②; **Refine** keeps the roster
   improving.

## Building the .exe

```cmd
build.bat
```

Output lands in `dist\CampaignScribe\` (folder bundle — keep all files
together; the .exe will not work alone). The CUDA build is ~4–5 GB because it
bundles CUDA + cuDNN + cuBLAS DLLs alongside `torch`, `whisperx`, `pyannote`,
and `ffmpeg.exe`. A slim installer and auto-update are on the roadmap
(Phase 5).

## Development

- Tests: `pytest` (full, including Tk GUI tests) or `pytest -m "not gui"`.
- Lint/format: `ruff check .` and `ruff format .` (CI enforces both).
- CI (`.github/workflows/ci.yml`): ruff, mypy (non-blocking), bandit, semgrep,
  pip-audit, pytest on Linux (non-gui) and Windows (full). CodeQL runs
  separately. Branch protection on `main` requires both CI jobs.
- Dependabot bumps tooling weekly; the ML stack (torch / whisperx / pyannote
  and friends) is hand-pinned and excluded from Dependabot. Bump it manually
  and verify with a real transcription run.
- Design specs, plans and spike notes live under `docs/superpowers/`.
- Every PR names its roadmap item in the **Roadmap** section of the PR
  template.

## Storage

- App data: `%APPDATA%\CampaignScribe\data.db`, `config.json`, `errors.log`
- Speaker library: `%APPDATA%\CampaignScribe\library\<campaign-slug>\`
  (`manifest.json` + immutable timestamped roster versions; per-campaign
  voice fingerprints in `fingerprints.npz`, never uploaded)
- AI-provider API keys + HF token: Windows Credential Manager (via
  `keyring`), never on disk.
- Audio files, transcripts, summaries: wherever you point the output folder.

Privacy details, including exactly what leaves the machine and when, are in
[PRIVACY.md](PRIVACY.md). Crash reporting is opt-in, default off, and scrubbed.

## Troubleshooting

- **"PyTorch not available" in status bar** — the venv or bundle has no
  working torch, or a CUDA build is on a machine without a matching driver.
  Delete `.venv` and re-run `setup_venv.bat`, or rebuild with `build.bat`.
- **HuggingFace 403 / cannot download diarization model** — accept the
  license on the pyannote model page and verify your HF token is set in
  Settings.
- **"<provider> rejected the API key"** — the key saved for that provider in
  Settings → AI model was rejected; re-paste it and use Test connection.
- **CUDA out of memory** — pick a smaller Whisper model (medium / small) in
  Settings.
- **Something else broke** — Help → Feedback & Support → Report a problem
  attaches a scrubbed diagnostics bundle; Tools → Open Logs Folder has
  `errors.log`.
