# Bundled Diarization Weights (no HuggingFace token) — Design

- **Status:** Designed (2026-10-04). Spike done the same day; decisions approved by Mike. Implements Feature Spec #7 (Model Licensing & Weight Bundling) from the ProtonDrive strategic folder.
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/bundled-diarization-weights`.
- **Planning issue:** private board #11 (Phase 3).
- **Source spec:** `H:\ProtonDrive\mrompel\My files\Audio Transcription\CampaignScribe\Feature Spec - Model Licensing and Weight Bundling.md` (2026-05-28).
- **Vault backlog (filed 2026-10-04):** legal check of redistribution + attribution before any paid release; reduce the ~4.7 GB package.

## Goal

Diarization works out of the box with **no HuggingFace account, token, or license click**. The `pyannote/speaker-diarization-community-1` weights ship inside the app and load from disk; the HuggingFace token disappears from the UI, the docs, and the privacy statement.

Success criteria:
1. A packaged build on a machine with no HuggingFace token and no HF cache diarizes a recording.
2. Output equals today's token path (spike: identical turns and segments on a 10-minute session clip).
3. No UI surface mentions a HuggingFace token; no pre-flight check requires one.
4. The VAD no longer depends on GitHub (`torch.hub`) for token-less users.
5. Third-party notices ship with the app and are reachable from the About box.

## Spike findings (2026-10-04, throwaway, recorded in project memory)

- The community-1 snapshot (revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`) is self-contained: `config.yaml` with relative `$model/...` paths, `segmentation/pytorch_model.bin` (5.9 MB), `embedding/pytorch_model.bin` (26.6 MB), `plda/plda.npz`, `plda/xvec_transform.npz`. 32 MB.
- `whisperx.diarize.DiarizationPipeline(model_name=<local dir>, token=None)` loads it with HuggingFace offline and an empty HF home; output on the GPU is turn-for-turn identical to loading by model id.
- whisperx 3.8.5's default **pyannote VAD loads from its own package asset** (`whisperx/assets/pytorch_model.bin`) with no token. The app's current no-token fallback to `vad_method="silero"` fetches `snakers4/silero-vad` from GitHub via `torch.hub` — a hidden network dependency and a different VAD than token users get.
- The full app transcribe path with no token + bundled VAD + local weights equals today's token path exactly (segments, speakers, voice embeddings).
- License: repo card `cc-by-4.0`; embedding card = WeSpeaker ResNet34 on VoxCeleb, CC-BY-4.0; `plda/` and `segmentation/` have no license line of their own (repo-level grant only) → the legal-check backlog item.
- Remaining first-run downloads **not** addressed here: faster-whisper models (public HF repos, no token) and the wav2vec2 alignment model (download.pytorch.org). They belong to First-Run Setup / slim distribution.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Ship the weights inside the app** (PyInstaller `datas`), not a first-run download from a mirror. | 32 MB next to a 4.7 GB bundle; no network step; nothing to host. (Mike, 2026-10-04) |
| 2 | **Remove the HuggingFace token** from Settings, pre-flight checks, Discover, Getting Started, PRIVACY.md and README; delete `config.save_huggingface_token` / `get_huggingface_token`. The user's existing keyring entry is left untouched. | Nothing uses it after this change. (Mike, 2026-10-04) |
| 3 | **Weights are fetched at build/setup time, not committed to git.** `scripts/fetch_diarization_weights.py` downloads the pinned revision with the developer's token into the git-ignored `models/speaker-diarization-community-1/` and verifies SHA-256 of every file. `setup_venv.bat` and `build.bat` call it. | Keeps 32 MB of binaries out of the public repo's history; the packaged release is the only redistribution point, which is what the legal check covers. A pinned revision + hashes make builds reproducible. |
| 4 | **Always use WhisperX's built-in pyannote VAD**; delete the Silero branch. | Same VAD token users have today; no GitHub dependency. |
| 5 | Missing weights is a **clear error**, never a silent HF download. | A broken install should say so; falling back to the Hub would need the token we just removed. |
| 6 | Attribution in a new `THIRD-PARTY-NOTICES.md` (bundled) and an About-box button that shows it. | CC-BY-4.0 §3(a) attribution; mirrors how PRIVACY.md is bundled and shown. |

## Architecture

```
scripts/fetch_diarization_weights.py   NEW  pinned-revision download + SHA-256 verify (dev/build only; never imported by the app)
models/                                NEW  git-ignored; holds speaker-diarization-community-1/ after fetch
app/core/models.py                     NEW  Tk-free path resolution + validation for bundled model folders
app/core/transcriber.py                MOD  no hf_token; always pyannote VAD; diarization from the bundled folder
app/config.py                          MOD  delete save/get_huggingface_token
app/ui/settings_dialog.py              MOD  remove the HuggingFace token row
app/ui/transcribe_tab.py, refine_tab.py, edit_profile_window.py   MOD  drop token pre-flight / plumbing
app/ui/app_window.py                   MOD  Getting Started text; About box "Third-party notices" button + dialog
THIRD-PARTY-NOTICES.md                 NEW  bundled; pyannote / WeSpeaker / VoxCeleb / VBx / Whisper / WhisperX / faster-whisper / CTranslate2
PRIVACY.md, README.md                  MOD  token removed; honest first-run download note
build.bat, CampaignScribe.spec, setup_venv.bat, .gitignore   MOD  fetch + bundle + ignore
```

### `scripts/fetch_diarization_weights.py`

```python
REPO_ID = "pyannote/speaker-diarization-community-1"
REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
FILES = {  # relative path -> sha256, computed 2026-10-04 from the pinned revision
    "config.yaml": "5ce2bfa9a938dc132cec1172592d65173cbb8f444ea1e4133f10f9391de155be",
    "segmentation/pytorch_model.bin": "7ad24338d844fb95985486eb1a464e32d229f6d7a03c9abe60f978bacf3f816e",
    "embedding/pytorch_model.bin": "6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929",
    "plda/plda.npz": "9b77bcd840692710dd3496f62ecfeed8d8e5f002fd991b785079b244eab7d255",
    "plda/xvec_transform.npz": "325f1ce8e48f7e55e9c8aa47e05d2766b7c48c4b25b8de8dd751e7a4cc5fbe8f",
}
DEST = <repo>/models/speaker-diarization-community-1

def sha256(path) -> str
def verify(dest) -> list[str]          # files missing or with wrong hash; [] = OK
def fetch(dest, token) -> None         # hf_hub_download each FILE at REVISION into dest (copies, no symlinks), then verify; raise on mismatch
def main(argv) -> int                  # already valid -> 0; token from HF_TOKEN env or keyring ("CampaignScribe","huggingface_token"); no token -> print instructions, return 2
```
- `verify` is pure and unit-tested with tmp files; `fetch` is never run in CI.
- The hashes above were computed from the pinned revision on 2026-10-04.

### `app/core/models.py`

```python
DIARIZATION_DIRNAME = "speaker-diarization-community-1"
REQUIRED_FILES = ("config.yaml", "segmentation/pytorch_model.bin", "embedding/pytorch_model.bin", "plda/plda.npz", "plda/xvec_transform.npz")

class MissingModelError(RuntimeError): ...

def models_root() -> Path              # frozen: Path(sys._MEIPASS) / "models"; source: <repo>/models
def diarization_dir() -> Path          # models_root() / DIARIZATION_DIRNAME, after checking REQUIRED_FILES exist; else MissingModelError
```
MissingModelError message: `"Speaker-diarization model files are missing from this installation ({missing}). Reinstall CampaignScribe, or in a development checkout run: python scripts/fetch_diarization_weights.py"`.

### Transcriber

- `TranscriptionPipeline.__init__(self, model_size="large-v3", force_cpu=False)` — `hf_token` removed.
- `_load_models`: `whisperx.load_model(self.model_size, self.device, compute_type=self.compute_type)` (no `vad_method`, no `use_auth_token`); `DiarizationPipeline(model_name=str(models.diarization_dir()), token=None, device=self.device)`.
- The stale comments about tokens and Silero are deleted.

### UI and config

- Settings: the "HuggingFace token" row, `hf_var`, `hf_entry`, `hf_show_var`, `_toggle_hf_visibility`, and the save line are removed.
- Transcribe `_start`: the HuggingFace pre-flight block is removed; `_worker` builds `TranscriptionPipeline(model_size=...)` without a token.
- Refine `_worker`, Edit Profile `_discover_from_audio`: no token read; Discover's message becomes `"Discover needs an AI provider set up in Settings (⚙).\n" + llm.not_ready_message()` and the check is `llm.provider_ready()` only.
- Getting Started: `"CampaignScribe needs one thing set up (Settings ⚙): an AI provider for speaker identification and summaries — Claude, Google Gemini, OpenRouter, or a free local model with Ollama / LM Studio.\n\nThen work left to right: Home → New session → Transcribe → Summarize. Refine improves your speaker profile from new audio."`
- `config.save_huggingface_token` / `get_huggingface_token` deleted (grep must find no callers). Diagnostics' `hf_...` redaction stays (harmless, protects old logs).
- About box: a "Third-party notices" button opening `NoticesDialog` (same pattern as `PrivacyDialog`: read-only text widget with the bundled file; embedded fallback one-liner if missing).

### Packaging

- `.gitignore`: `/models/`.
- `setup_venv.bat`: after the installs, runs `"%PY%" scripts\fetch_diarization_weights.py`; a non-zero exit prints a warning (setup still succeeds; Transcribe will show MissingModelError until fetched).
- `build.bat`: runs the fetch script first and **aborts the build** on non-zero; adds `--add-data "models\speaker-diarization-community-1;models\speaker-diarization-community-1"` and `--add-data "THIRD-PARTY-NOTICES.md;."`. `CampaignScribe.spec` gets the same two `datas` entries.

### Docs

- PRIVACY.md: the key bullet drops the HuggingFace token; the "Sent to HuggingFace" section becomes **"Model downloads (first use only)"**: "The speech-recognition models (Whisper) are downloaded from Hugging Face's public servers, and a word-alignment model from pytorch.org, the first time they are needed. No account, token, audio, or transcripts are sent. The speaker-diarization model ships with CampaignScribe and never downloads."
- README: Prerequisites drop the token bullet and its license note; Settings bullet drops "HuggingFace token"; Storage drops "+ HF token"; Troubleshooting replaces the HF 403 entry with "Speaker-diarization model files are missing → reinstall, or run the fetch script in a dev checkout"; Development notes the fetch script.

## Testing

Unit: `tests/unit/test_models_paths.py` — source vs frozen root (monkeypatch `sys.frozen` / `sys._MEIPASS`), all files present → path, each missing file → MissingModelError naming it. `tests/unit/test_fetch_weights.py` — `sha256`/`verify` on tmp files (OK, missing, wrong hash); `main` returns 0 when already valid without network, 2 with no token. `tests/unit/test_transcriber_loading.py` — stub `whisperx.load_model` and `whisperx.diarize.DiarizationPipeline`; assert load_model kwargs have no `vad_method`/`use_auth_token`, DiarizationPipeline gets `model_name=<bundled dir>` and `token=None`; MissingModelError propagates when weights absent.

GUI: Settings has no `hf_var`; Transcribe pre-flight passes with a provider ready and no token (existing tests updated: `test_edit_profile_discover_closed.py`, any test patching `get_huggingface_token`); About → NoticesDialog builds and shows "pyannote".

Repo-wide check: `grep -rn -i "huggingface token\|get_huggingface_token\|hf_token" app README.md PRIVACY.md` returns nothing.

Manual (Mike's PC, before PR): `run_dev.bat` transcribe of a test clip with the weights fetched; then `build.bat` and run the packaged exe on the same clip with the HF cache folder temporarily renamed.

## Out of scope

Bundling Whisper / alignment models (first-run downloads remain — First-Run Setup / slim distribution); package size reduction (backlog); pyannoteAI premium models; the legal opinion itself (backlog); any ML pin change.
