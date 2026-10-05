# Library locks

`gpu.txt` and `cpu.txt` are the exact, fully transitive Python library sets that
first-run setup installs into the user's environment with
`pip install --no-deps -r locks/<profile>.txt`. Because of `--no-deps`, every
package must be listed. They are generated, never hand-edited.

The setup compares `bootstrap/core.lock_sha256()` (CRLF-normalised; the installed bootstrap cannot import `scripts/`) of the
shipped lock with the one recorded in `cs-setup.json`; any change here triggers a
re-setup of the same profile on the next launch.

## When to regenerate

- Any pin change in `requirements.txt` (torch, whisperx, pyannote, transformers, ...).
- A dependabot / ML-stack bump, or a security update of a transitive package.
- A new Python minor version for the bundled runtime.

## How to regenerate

Use a clean, app-only venv per profile, at a SHORT path (a long venv path breaks
torch DLL loading with WinError 206), built with the same Python as the shipped runtime.

```powershell
py -3.13 -m venv C:\cs-lock\gpu
$py = "C:\cs-lock\gpu\Scripts\python.exe"
& $py -m pip install --upgrade pip
# step 1: app deps from requirements.txt (no pyinstaller, no requirements-dev.txt)
& $py -m pip install anthropic google-genai openai keyring ffmpeg-python python-docx darkdetect "sentry-sdk~=2.71" faster-whisper==1.2.1 whisperx==3.8.6 pyannote.audio==4.0.4 transformers==4.57.6 huggingface_hub==0.36.2 lightning==2.6.6 pytorch-lightning==2.6.6
# step 2: drop torchvision, force torch/torchaudio (use .../whl/cpu and +cpu for the cpu profile)
& $py -m pip uninstall -y torchvision
& $py -m pip install --force-reinstall --no-deps --extra-index-url https://download.pytorch.org/whl/cu128 torch==2.11.0+cu128 torchaudio==2.11.0+cu128
# sanity (from the repo root), then generate
& $py -c "import torch, whisperx, pyannote.audio, faster_whisper, app"
.venv\Scripts\python scripts\make_locks.py --profile gpu --venv C:\cs-lock\gpu --out locks\gpu.txt
```

Repeat with `C:\cs-lock\cpu`, the `cpu` index / `+cpu` builds and `--profile cpu`.
Then prove it: in a third clean venv run `pip install --no-deps -r locks/gpu.txt`,
`pip install -r requirements-dev.txt`, run the full test suite and a real GPU
transcription. Delete `C:\cs-lock` afterwards.

## What is excluded

`pip`, `setuptools` (nothing imports it at runtime; proven by a full test run and
GPU transcription without it), `wheel`, `torchvision` (unused; breaks torchmetrics
under torch 2.11), `pyinstaller` (not installed in the clean env) and dev-only
tooling from `requirements-dev.txt`.
