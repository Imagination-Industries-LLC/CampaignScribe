# Bundled Diarization Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the pyannote community-1 diarization weights inside CampaignScribe, load them from disk with no HuggingFace token, always use WhisperX's built-in VAD, remove the token from the whole app, and ship third-party notices.

**Architecture:** A dev/build-only script fetches the pinned revision into a git-ignored `models/` folder and verifies SHA-256 hashes. A Tk-free `app/core/models.py` resolves that folder (source checkout or PyInstaller bundle) and raises a clear `MissingModelError`. The transcriber loads WhisperX without VAD/token arguments and passes the folder to `DiarizationPipeline`. UI, config, docs lose the token; an About-box button shows a bundled `THIRD-PARTY-NOTICES.md`; `build.bat` fetches and bundles the weights, notices and PRIVACY.md.

**Tech Stack:** Python 3.11, Tkinter, whisperx 3.8.5, pyannote.audio 4.0.4, huggingface_hub 0.36.2 (fetch script only), PyInstaller, pytest. Windows + PowerShell 5.1; run everything through `.venv\Scripts\python`.

**Spec:** `docs/superpowers/specs/2026-10-04-bundled-diarization-weights-design.md` — read it first.

## Global Constraints

- Branch `feature/bundled-diarization-weights` off `main` (spec committed). One PR at the end; Mike merges.
- Every commit: `.venv\Scripts\python -m ruff check .` and `.venv\Scripts\python -m ruff format .` clean; `.venv\Scripts\python -m bandit -q -r app -ll` exits 0 before the final commit. Single-line commit messages. **No AI attribution, no `Co-Authored-By`.**
- `.venv\Scripts\python -m pytest -q` stays green after every task (442 at branch start). CI never downloads weights: no test may touch the network or need `models/` populated.
- No ML pin changes; no new runtime dependency; `.github/dependabot.yml` untouched.
- Pinned revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`; repo id `pyannote/speaker-diarization-community-1`; folder name `speaker-diarization-community-1`; required files exactly `config.yaml`, `segmentation/pytorch_model.bin`, `embedding/pytorch_model.bin`, `plda/plda.npz`, `plda/xvec_transform.npz` with SHA-256 values from the spec.
- MissingModelError text exactly: `"Speaker-diarization model files are missing from this installation ({missing}). Reinstall CampaignScribe, or in a development checkout run: python scripts/fetch_diarization_weights.py"` where `{missing}` is the comma-joined relative paths.
- The user's keyring entry `("CampaignScribe", "huggingface_token")` is never written or deleted by the app; only the fetch script reads it.
- No references to the predecessor product name. Every subprocess (none expected) uses `CREATE_NO_WINDOW`.

## Review Focus

1. A weights folder whose files exist but are **truncated or corrupt** must not reach pyannote silently in a dev checkout — the fetch script's `verify` catches wrong hashes; the app's `diarization_dir()` only checks presence (cheap at every run). → Task 1 `test_verify_detects_wrong_hash`; documented as intended in Task 2.
2. The fetch script run with weights **already present and valid** must succeed without network or token (setup re-runs, CI-like machines). → Task 1 `test_main_valid_needs_no_token_or_network`.
3. A frozen build where `sys._MEIPASS` has the folder but one file is missing must name exactly that file. → Task 2 `test_missing_file_is_named`.
4. Discover, Transcribe and Refine must each work with **no token anywhere** — no hidden `get_huggingface_token` call left behind. → Task 3 `test_no_token_api_left` (repo grep test).
5. The notices dialog must render even if the bundled file is missing (fallback text), like Privacy. → Task 4 `test_notices_fallback_when_missing`.

---

### Task 1: `scripts/fetch_diarization_weights.py`

**Files:**
- Create: `scripts/fetch_diarization_weights.py`, `scripts/__init__.py` (empty, so tests can import)
- Modify: `.gitignore` (add `/models/`)
- Test: `tests/unit/test_fetch_weights.py`

**Interfaces:**
- Produces: `REPO_ID`, `REVISION`, `FILES: dict[str, str]`, `DEFAULT_DEST: Path`, `sha256(path) -> str`, `verify(dest: Path) -> list[str]`, `fetch(dest: Path, token: str) -> None`, `main(argv: list[str] | None = None, *, dest: Path | None = None) -> int`.

- [ ] **Step 1: Failing tests**

Create `tests/unit/test_fetch_weights.py`:
```python
"""fetch_diarization_weights: hashing, verification, and main() exit codes (no network)."""

from __future__ import annotations

import hashlib

import pytest

from scripts import fetch_diarization_weights as fw


def _write_valid(dest, monkeypatch):
    """Write fake files and point FILES at their real hashes."""
    files = {}
    for rel in fw.FILES:
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        data = f"fake {rel}".encode()
        p.write_bytes(data)
        files[rel] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(fw, "FILES", files)
    return files


def test_pins():
    assert fw.REPO_ID == "pyannote/speaker-diarization-community-1"
    assert fw.REVISION == "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
    assert set(fw.FILES) == {
        "config.yaml",
        "segmentation/pytorch_model.bin",
        "embedding/pytorch_model.bin",
        "plda/plda.npz",
        "plda/xvec_transform.npz",
    }
    assert fw.FILES["embedding/pytorch_model.bin"] == (
        "6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929"
    )
    assert fw.DEFAULT_DEST.name == "speaker-diarization-community-1"
    assert fw.DEFAULT_DEST.parent.name == "models"


def test_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert fw.sha256(p) == hashlib.sha256(b"abc").hexdigest()


def test_verify_ok_and_missing(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    assert fw.verify(tmp_path) == []
    (tmp_path / "plda" / "plda.npz").unlink()
    assert fw.verify(tmp_path) == ["plda/plda.npz"]


def test_verify_detects_wrong_hash(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    (tmp_path / "config.yaml").write_bytes(b"tampered")
    assert fw.verify(tmp_path) == ["config.yaml"]


def test_main_valid_needs_no_token_or_network(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    monkeypatch.setattr(fw, "fetch", lambda *a, **k: pytest.fail("must not fetch"))
    monkeypatch.setattr(fw, "_token", lambda: pytest.fail("must not read a token"))
    assert fw.main([], dest=tmp_path) == 0


def test_main_without_token_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fw, "_token", lambda: "")
    assert fw.main([], dest=tmp_path) == 2
    assert "huggingface.co/pyannote/speaker-diarization-community-1" in capsys.readouterr().out


def test_main_fetches_then_verifies(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fw, "_token", lambda: "hf_x")

    def _fake_fetch(dest, token):
        calls.append(token)
        _write_valid(dest, monkeypatch)

    monkeypatch.setattr(fw, "fetch", _fake_fetch)
    assert fw.main([], dest=tmp_path) == 0
    assert calls == ["hf_x"]


def test_main_hash_mismatch_after_fetch_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "_token", lambda: "hf_x")
    monkeypatch.setattr(fw, "fetch", lambda dest, token: None)  # writes nothing
    assert fw.main([], dest=tmp_path) == 1
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_fetch_weights.py -v` → FAIL (`ModuleNotFoundError: No module named 'scripts'`).

- [ ] **Step 3: Implement**

Create empty `scripts/__init__.py`. Create `scripts/fetch_diarization_weights.py`:
```python
"""Fetch the pinned pyannote community-1 diarization weights into models/ (dev/build only).

The app never imports this. setup_venv.bat and build.bat run it; it needs a
HuggingFace token once (HF_TOKEN env var, or the keyring entry the old app
Settings stored). Already-valid weights need no token and no network.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

REPO_ID = "pyannote/speaker-diarization-community-1"
REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
FILES: dict[str, str] = {
    "config.yaml": "5ce2bfa9a938dc132cec1172592d65173cbb8f444ea1e4133f10f9391de155be",
    "segmentation/pytorch_model.bin": "7ad24338d844fb95985486eb1a464e32d229f6d7a03c9abe60f978bacf3f816e",
    "embedding/pytorch_model.bin": "6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929",
    "plda/plda.npz": "9b77bcd840692710dd3496f62ecfeed8d8e5f002fd991b785079b244eab7d255",
    "plda/xvec_transform.npz": "325f1ce8e48f7e55e9c8aa47e05d2766b7c48c4b25b8de8dd751e7a4cc5fbe8f",
}
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "models" / "speaker-diarization-community-1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(dest: Path) -> list[str]:
    """Relative paths that are missing or have the wrong hash; [] means OK."""
    bad = []
    for rel, digest in FILES.items():
        p = Path(dest) / rel
        if not p.is_file() or sha256(p) != digest:
            bad.append(rel)
    return bad


def _token() -> str:
    tok = os.environ.get("HF_TOKEN", "").strip()
    if tok:
        return tok
    try:
        import keyring

        return (keyring.get_password("CampaignScribe", "huggingface_token") or "").strip()
    except Exception:  # noqa: BLE001 - no keyring backend is fine; we just have no token
        return ""


def fetch(dest: Path, token: str) -> None:
    from huggingface_hub import hf_hub_download

    for rel in FILES:
        src = hf_hub_download(REPO_ID, rel, revision=REVISION, token=token)
        target = Path(dest) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)  # real copy: no symlinks into the HF cache


def main(argv: list[str] | None = None, *, dest: Path | None = None) -> int:
    dest = Path(dest or DEFAULT_DEST)
    if not verify(dest):
        print(f"[fetch_diarization_weights] OK — weights already present at {dest}")
        return 0
    token = _token()
    if not token:
        print(
            "[fetch_diarization_weights] No HuggingFace token found.\n"
            "  1) Accept the license at https://huggingface.co/pyannote/speaker-diarization-community-1\n"
            "  2) Create a read token at https://huggingface.co/settings/tokens\n"
            "  3) Re-run with:  set HF_TOKEN=hf_...  then  python scripts\\fetch_diarization_weights.py"
        )
        return 2
    fetch(dest, token)
    bad = verify(dest)
    if bad:
        print(f"[fetch_diarization_weights] Hash check FAILED for: {', '.join(bad)}")
        return 1
    print(f"[fetch_diarization_weights] OK — fetched {REPO_ID}@{REVISION[:8]} to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```
Append to `.gitignore`:
```
# Bundled model weights (fetched by scripts/fetch_diarization_weights.py; never committed)
/models/
```

- [ ] **Step 4: Run tests, then fetch for real once**

Run: `.venv\Scripts\python -m pytest tests/unit/test_fetch_weights.py -v` → 8 PASS.
Run: `.venv\Scripts\python scripts\fetch_diarization_weights.py` → prints `OK — fetched …` (the dev machine's keyring holds a token) or `OK — weights already present`; then `git status --short` must NOT list anything under `models/`.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add scripts/__init__.py scripts/fetch_diarization_weights.py tests/unit/test_fetch_weights.py .gitignore
git commit -m "build: fetch script for pinned pyannote community-1 weights with SHA-256 verification"
```

---

### Task 2: `app/core/models.py` + transcriber loads bundled weights, always pyannote VAD

**Files:**
- Create: `app/core/models.py`
- Modify: `app/core/transcriber.py` (`__init__`, `_load_models`)
- Test: `tests/unit/test_models_paths.py`, `tests/unit/test_transcriber_loading.py`

**Interfaces:**
- Produces: `models.DIARIZATION_DIRNAME`, `models.REQUIRED_FILES`, `models.MissingModelError(RuntimeError)`, `models.models_root() -> Path`, `models.diarization_dir() -> Path`. `TranscriptionPipeline(model_size="large-v3", force_cpu=False)` (no `hf_token`).

- [ ] **Step 1: Failing tests**

Create `tests/unit/test_models_paths.py`:
```python
"""models: locate the bundled diarization weights in a checkout or a frozen build."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core import models


def _populate(root: Path) -> Path:
    d = root / models.DIARIZATION_DIRNAME
    for rel in models.REQUIRED_FILES:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(b"x")
    return d


def test_source_root_is_repo_models():
    assert models.models_root() == Path(models.__file__).resolve().parents[2] / "models"


def test_frozen_root_uses_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert models.models_root() == tmp_path / "models"


def test_diarization_dir_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    d = _populate(tmp_path)
    assert models.diarization_dir() == d


def test_missing_file_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    d = _populate(tmp_path)
    (d / "plda" / "xvec_transform.npz").unlink()
    with pytest.raises(models.MissingModelError) as ei:
        models.diarization_dir()
    assert str(ei.value) == (
        "Speaker-diarization model files are missing from this installation "
        "(plda/xvec_transform.npz). Reinstall CampaignScribe, or in a development "
        "checkout run: python scripts/fetch_diarization_weights.py"
    )


def test_missing_folder_names_every_file(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    with pytest.raises(models.MissingModelError) as ei:
        models.diarization_dir()
    for rel in models.REQUIRED_FILES:
        assert rel in str(ei.value)
```
Create `tests/unit/test_transcriber_loading.py`:
```python
"""TranscriptionPipeline loads WhisperX with its built-in VAD and diarization from the bundled folder."""

from __future__ import annotations

import inspect

import pytest

from app.core import models, transcriber


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    import whisperx
    import whisperx.diarize as wd

    calls = {}
    monkeypatch.setattr(whisperx, "load_model", lambda *a, **k: calls.setdefault("load", (a, k)) or object())

    class _DP:
        def __init__(self, **k):
            calls["diarize"] = k

    monkeypatch.setattr(wd, "DiarizationPipeline", _DP)
    monkeypatch.setattr(models, "diarization_dir", lambda: tmp_path / "weights")
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})
    return calls


def test_constructor_has_no_hf_token():
    assert "hf_token" not in inspect.signature(transcriber.TranscriptionPipeline.__init__).parameters


def test_load_uses_builtin_vad_and_bundled_diarization(stubs, tmp_path):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p._load_models()
    args, kwargs = stubs["load"]
    assert args == ("small", "cpu")
    assert kwargs == {"compute_type": "int8"}  # no vad_method, no use_auth_token
    assert stubs["diarize"] == {"model_name": str(tmp_path / "weights"), "token": None, "device": "cpu"}


def test_missing_weights_raise_clear_error(monkeypatch):
    import whisperx

    monkeypatch.setattr(whisperx, "load_model", lambda *a, **k: object())
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})

    def _missing():
        raise models.MissingModelError("Speaker-diarization model files are missing …")

    monkeypatch.setattr(models, "diarization_dir", _missing)
    with pytest.raises(models.MissingModelError):
        transcriber.TranscriptionPipeline(model_size="small")._load_models()
```
(If `check_gpu` is imported into `transcriber` under a different name, read the file and patch the name it actually uses.)

- [ ] **Step 2: Run, expect failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_models_paths.py tests/unit/test_transcriber_loading.py -v` → FAIL (`ImportError: cannot import name 'models'`).

- [ ] **Step 3: Implement**

Create `app/core/models.py`:
```python
"""Locate model files bundled with CampaignScribe (Tk-free).

Diarization weights live in <root>/models/speaker-diarization-community-1, where
<root> is the PyInstaller bundle dir when frozen, else the repo root. Presence
is checked on every run (cheap); content hashes are checked at fetch/build time
by scripts/fetch_diarization_weights.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

DIARIZATION_DIRNAME = "speaker-diarization-community-1"
REQUIRED_FILES = (
    "config.yaml",
    "segmentation/pytorch_model.bin",
    "embedding/pytorch_model.bin",
    "plda/plda.npz",
    "plda/xvec_transform.npz",
)


class MissingModelError(RuntimeError):
    """A bundled model folder is absent or incomplete."""


def models_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "models"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "models"


def diarization_dir() -> Path:
    d = models_root() / DIARIZATION_DIRNAME
    missing = [rel for rel in REQUIRED_FILES if not (d / rel).is_file()]
    if missing:
        raise MissingModelError(
            f"Speaker-diarization model files are missing from this installation "
            f"({', '.join(missing)}). Reinstall CampaignScribe, or in a development "
            f"checkout run: python scripts/fetch_diarization_weights.py"
        )
    return d
```
In `app/core/transcriber.py`:
- `__init__(self, model_size: str = "large-v3", force_cpu: bool = False)`; delete `self.hf_token = ...`.
- Replace the body of `_load_models` with:
```python
    def _load_models(self) -> None:
        if self._model is None:
            import whisperx

            # whisperx 3.8.5's default VAD (pyannote) loads from a file inside the
            # whisperx package: no HuggingFace token and no network needed.
            self._model = whisperx.load_model(
                self.model_size, self.device, compute_type=self.compute_type
            )
        if self._diarize is None:
            from whisperx.diarize import DiarizationPipeline

            from app.core import models

            # Bundled pyannote community-1 weights (CC-BY-4.0); see THIRD-PARTY-NOTICES.md.
            self._diarize = DiarizationPipeline(
                model_name=str(models.diarization_dir()), token=None, device=self.device
            )
```
(Keep the import of `models` inside the function so tests can patch `models.diarization_dir`. If ruff flags the import position, move `from app.core import models` to the module top and keep calling `models.diarization_dir()` — the test patches the module attribute either way.)

- [ ] **Step 4: Run tests**

Run the two new test files → all PASS. Run `.venv\Scripts\python -m pytest -q` → all PASS. (The UI workers still pass `hf_token=` until Task 3, but no test executes a real `TranscriptionPipeline` constructor from a worker — `test_edit_profile_discover_closed.py` patches the class with a fake that accepts any kwargs — so the suite stays green; Task 3 removes those arguments.)

- [ ] **Step 5: Commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/models.py app/core/transcriber.py tests/unit/test_models_paths.py tests/unit/test_transcriber_loading.py
git commit -m "feat(transcriber): load bundled diarization weights offline; always use whisperx's built-in VAD; no HF token"
```

---

### Task 3: Remove the HuggingFace token from config and UI

**Files:**
- Modify: `app/config.py` (delete `save_huggingface_token`, `get_huggingface_token`)
- Modify: `app/ui/settings_dialog.py` (HF row lines ~35-46, `_toggle_hf_visibility`, the save line)
- Modify: `app/ui/transcribe_tab.py` (pre-flight block ~360-368; worker `hf = ...` and `hf_token=hf`)
- Modify: `app/ui/refine_tab.py` (`hf = ...`, `hf_token=hf`)
- Modify: `app/ui/edit_profile_window.py` (`_discover_from_audio` check/message; `hf_token=hf`)
- Modify: `app/ui/app_window.py` (`_show_getting_started` text)
- Modify: `tests/gui/test_edit_profile_discover_closed.py` (drop the `get_huggingface_token` patch)
- Test: `tests/unit/test_no_hf_token.py` (new), `tests/gui/test_settings_llm.py` (one test)

**Interfaces:** Consumes Task 2's `TranscriptionPipeline(model_size=...)`.

- [ ] **Step 1: Failing tests**

Create `tests/unit/test_no_hf_token.py`:
```python
"""No HuggingFace token remains anywhere in the app or user-facing docs."""

from __future__ import annotations

import re
from pathlib import Path

from app import config

ROOT = Path(__file__).resolve().parents[2]


def test_config_has_no_token_api():
    assert not hasattr(config, "get_huggingface_token")
    assert not hasattr(config, "save_huggingface_token")


def test_no_token_api_left():
    pat = re.compile(r"get_huggingface_token|save_huggingface_token|hf_token|HuggingFace token", re.I)
    hits = []
    for p in (ROOT / "app").rglob("*.py"):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert hits == []
```
Append to `tests/gui/test_settings_llm.py`:
```python
def test_settings_has_no_huggingface_row(root):
    dlg = _open(root)
    try:
        assert not hasattr(dlg, "hf_var")
        labels = []

        def _walk(w):
            for c in w.winfo_children():
                try:
                    labels.append(str(c.cget("text")))
                except tk.TclError:
                    pass
                _walk(c)

        _walk(dlg)
        assert not any("HuggingFace" in t for t in labels)
    finally:
        dlg.destroy()
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_no_hf_token.py tests/gui/test_settings_llm.py -v -k "token or huggingface"` → FAIL.

- [ ] **Step 3: Implement**

- `app/config.py`: delete both functions (and nothing else).
- `settings_dialog.py`: delete the HF label/entry/Show block and its `row += 1`; delete `_toggle_hf_visibility`; delete `config.save_huggingface_token(self.hf_var.get().strip())`.
- `transcribe_tab.py`: delete the whole `if not config.get_huggingface_token(): ... return` block in `_start`; in `_worker` delete `hf = config.get_huggingface_token()` and the `hf_token=hf,` argument.
- `refine_tab.py`: delete `hf = config.get_huggingface_token()` and `hf_token=hf,`.
- `edit_profile_window.py` `_discover_from_audio`: replace the `hf = ...` line and the `if not llm.provider_ready() or not hf:` block with
```python
        if not llm.provider_ready():
            messagebox.showerror(
                "CampaignScribe",
                "Discover needs an AI provider set up in Settings (⚙).\n" + llm.not_ready_message(),
            )
            return
```
and delete `hf_token=hf,` in the worker.
- `app_window.py` `_show_getting_started` message becomes exactly:
```python
            "CampaignScribe needs one thing set up (Settings ⚙): an AI provider for "
            "speaker identification and summaries — Claude, Google Gemini, OpenRouter, "
            "or a free local model with Ollama / LM Studio.\n\n"
            "Then work left to right: Home → New session → Transcribe → "
            "Summarize. Refine improves your speaker profile from new audio.",
```
- `tests/gui/test_edit_profile_discover_closed.py`: delete the `monkeypatch.setattr("app.config.get_huggingface_token", ...)` line.
- `app/core/diagnostics.py`: leave the `hf_...` redaction as is, but if its comment contains the literal words "HuggingFace token" the grep test fails — reword the comment to `# Redact API keys/tokens (Anthropic sk-..., Hugging Face hf_...).` so it no longer matches `HuggingFace token` (case-insensitive match is on the two-word phrase).

- [ ] **Step 4: Run tests**

Run the new tests → PASS. Run `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app tests
git commit -m "feat: remove the HuggingFace token from Settings, pre-flight checks, Discover and Getting Started"
```

---

### Task 4: Third-party notices file, loader and About-box dialog

**Files:**
- Create: `THIRD-PARTY-NOTICES.md`, `app/core/notices.py`
- Modify: `app/ui/app_window.py` (`NoticesDialog` class; "Third-party notices" button in `AboutDialog` btnrow before "Close")
- Test: `tests/unit/test_notices.py`, `tests/smoke/test_notices_dialog.py`

**Interfaces:** Produces `notices.load_notices_text() -> str`, `notices._notices_path() -> Path`, `notices._FALLBACK: str`, `app_window.NoticesDialog(master)`.

- [ ] **Step 1: Failing tests**

`tests/unit/test_notices.py`:
```python
from __future__ import annotations

from app.core import notices


def test_loads_bundled_file():
    text = notices.load_notices_text()
    for needle in ("pyannote", "CC-BY-4.0", "WeSpeaker", "VoxCeleb", "VBx", "Whisper", "WhisperX", "faster-whisper", "CTranslate2"):
        assert needle in text, needle


def test_notices_fallback_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(notices, "_notices_path", lambda: tmp_path / "nope.md")
    assert notices.load_notices_text() == notices._FALLBACK
    assert "THIRD-PARTY-NOTICES" in notices._FALLBACK
```
`tests/smoke/test_notices_dialog.py`:
```python
"""Headless smoke: the third-party notices dialog renders the bundled text."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None, "error": "stub", "smi_gpu_name": None},
    )
    from app.data import db

    db.init_db()
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    win.withdraw()
    win.update_idletasks()
    try:
        yield win
    finally:
        win.destroy()


def test_notices_dialog_shows_text(app):
    from app.ui.app_window import NoticesDialog

    dlg = NoticesDialog(app)
    app.update_idletasks()
    try:
        texts = []

        def _walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Text):
                    texts.append(c.get("1.0", "end"))
                _walk(c)

        _walk(dlg)
        assert texts and "pyannote" in texts[0]
    finally:
        dlg.destroy()
```

- [ ] **Step 2: Run, expect failure** → `ImportError` / `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`THIRD-PARTY-NOTICES.md`:
```markdown
# Third-party notices

CampaignScribe includes or downloads the following third-party models and software.

## Bundled with CampaignScribe

### pyannote speaker-diarization-community-1 (pipeline and weights)
- Source: https://huggingface.co/pyannote/speaker-diarization-community-1 (revision 3533c8cf)
- License: Creative Commons Attribution 4.0 International (CC-BY-4.0) — https://creativecommons.org/licenses/by/4.0/
- Copyright: pyannote / pyannoteAI. Redistributed unmodified.
- Components:
  - Segmentation model — pyannote.
  - Speaker-embedding model — WeSpeaker ResNet34 trained on VoxCeleb (copied from pyannote/wespeaker-voxceleb-resnet34-LM); follows the VoxCeleb dataset license, CC-BY-4.0. WeSpeaker: https://github.com/wenet-e2e/wespeaker
  - PLDA / clustering parameters — VBx (Brno University of Technology, Speech@FIT), integrated into pyannote.audio by Jiangyu Han and Petr Pálka.

### pyannote.audio (library)
- License: MIT — https://github.com/pyannote/pyannote-audio

### WhisperX
- License: BSD-2-Clause — https://github.com/m-bain/whisperX
- Includes a voice-activity-detection model file used by CampaignScribe.

### faster-whisper / CTranslate2
- faster-whisper: MIT — https://github.com/SYSTRAN/faster-whisper
- CTranslate2: MIT — https://github.com/OpenNMT/CTranslate2

## Downloaded on first use (not bundled)

### OpenAI Whisper models (CTranslate2 conversions by Systran)
- License: MIT — https://github.com/openai/whisper

### wav2vec2 alignment models (via torchaudio)
- License: see https://pytorch.org/audio/stable/pipelines.html

## Citations
- Bredin, H. "pyannote.audio 2.1 speaker diarization pipeline: principle, benchmark, and recipe." Interspeech 2023.
- Wang, H. et al. "Wespeaker: A research and production oriented speaker embedding learning toolkit." ICASSP 2023.
- Landini, F. et al. "Bayesian HMM clustering of x-vector sequences (VBx) in speaker diarization." Computer Speech & Language, 2022.
- Nagrani, A., Chung, J. S., Zisserman, A. "VoxCeleb: a large-scale speaker identification dataset." Interspeech 2017.
```
`app/core/notices.py`:
```python
"""Third-party notices text (Tk-free). THIRD-PARTY-NOTICES.md is bundled like PRIVACY.md."""

from __future__ import annotations

import sys
from pathlib import Path

_FALLBACK = (
    "CampaignScribe bundles the pyannote speaker-diarization-community-1 model "
    "(CC-BY-4.0) and uses WhisperX, faster-whisper and CTranslate2. See "
    "THIRD-PARTY-NOTICES.md in the installation folder or the project repository "
    "for full attributions."
)


def _notices_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[2]
    return base / "THIRD-PARTY-NOTICES.md"


def load_notices_text() -> str:
    try:
        return _notices_path().read_text(encoding="utf-8")
    except (OSError, ValueError):
        return _FALLBACK
```
`app/ui/app_window.py`: import `notices` alongside `privacy` (`from app.core import library, llm, notices, privacy`). Add `class NoticesDialog(tk.Toplevel)` directly after `PrivacyDialog`: same structure as `PrivacyDialog` (title `"Third-party notices — CampaignScribe"`, header label `"Third-party notices"`, the read-only Text filled with `notices.load_notices_text()`, a links frame with only the Close button), same centring code. In `AboutDialog`, before the Close button in `btnrow`: `ttk.Button(btnrow, text="Third-party notices", command=lambda: NoticesDialog(self)).pack(side="left", padx=4)`.

- [ ] **Step 4: Run tests** → new tests PASS; full suite PASS.

- [ ] **Step 5: Commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add THIRD-PARTY-NOTICES.md app/core/notices.py app/ui/app_window.py tests/unit/test_notices.py tests/smoke/test_notices_dialog.py
git commit -m "feat: third-party notices (pyannote CC-BY-4.0 and the Whisper stack) bundled and shown from About"
```

---

### Task 5: Packaging, PRIVACY.md, README, full gate

**Files:**
- Modify: `build.bat`, `CampaignScribe.spec`, `setup_venv.bat`, `PRIVACY.md`, `README.md`, `tests/unit/test_packaging_lists.py`, `tests/smoke/test_privacy_dialog.py` (only if it asserts the old HuggingFace section)

- [ ] **Step 1: Failing packaging test**

Append to `tests/unit/test_packaging_lists.py`:
```python
def test_build_fetches_and_bundles_weights_notices_and_privacy():
    bat = _read("build.bat")
    spec = _read("CampaignScribe.spec")
    assert "scripts\\fetch_diarization_weights.py" in bat
    assert bat.index("fetch_diarization_weights") < bat.index("PyInstaller")
    for needle in (
        '--add-data "models\\speaker-diarization-community-1;models\\speaker-diarization-community-1"',
        '--add-data "THIRD-PARTY-NOTICES.md;."',
        '--add-data "PRIVACY.md;."',
    ):
        assert needle in bat, needle
    assert "('models\\\\speaker-diarization-community-1', 'models\\\\speaker-diarization-community-1')" in spec
    assert "('THIRD-PARTY-NOTICES.md', '.')" in spec


def test_setup_venv_runs_fetch():
    assert "scripts\\fetch_diarization_weights.py" in _read("setup_venv.bat")


def test_privacy_and_readme_have_no_token():
    for name in ("PRIVACY.md", "README.md"):
        text = _read(name)
        assert "HuggingFace token" not in text and "HF token" not in text, name
    assert "Model downloads (first use only)" in _read("PRIVACY.md")
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement**

`build.bat`: after the venv check and before the PyInstaller line, insert
```bat
echo Fetching bundled diarization weights...
"%PY%" scripts\fetch_diarization_weights.py
if errorlevel 1 (
    echo ERROR: diarization weights missing or invalid; see message above.
    exit /b 1
)
```
and add, after `--add-data "assets;assets" ^`:
```bat
    --add-data "PRIVACY.md;." ^
    --add-data "THIRD-PARTY-NOTICES.md;." ^
    --add-data "models\speaker-diarization-community-1;models\speaker-diarization-community-1" ^
```
`CampaignScribe.spec` `datas` list gains `('THIRD-PARTY-NOTICES.md', '.')` and `('models\\speaker-diarization-community-1', 'models\\speaker-diarization-community-1')`.

`setup_venv.bat`: before the final `echo [setup_venv] Done...` insert
```bat
echo.
echo [setup_venv] Fetching bundled diarization weights...
"%PY%" scripts\fetch_diarization_weights.py
if errorlevel 1 echo [setup_venv] WARNING: weights not fetched; Transcribe will report missing model files until you run scripts\fetch_diarization_weights.py
```

`PRIVACY.md`: the key bullet becomes `- **Your AI-provider API keys** — stored in Windows Credential Manager; each is sent only to its own service to authenticate.`; replace the whole `## Sent to HuggingFace` section with
```markdown
## Model downloads (first use only)
- The speech-recognition models (Whisper) are downloaded from Hugging Face's public servers, and a word-alignment model from pytorch.org, the first time they are needed. No account, token, audio, or transcripts are sent.
- The speaker-diarization model ships with CampaignScribe and never downloads.
```
If `tests/smoke/test_privacy_dialog.py` asserts anything from the removed section, update it to assert `"Model downloads (first use only)"`.

`README.md`:
- Layout → Settings bullet: remove "HuggingFace token, " (keep wrapping ≤ ~80 cols).
- Prerequisites: delete the HuggingFace token bullet and the license-click paragraph under it; add a line: `- Nothing else: speaker diarization ships with the app (no Hugging Face account needed). The Whisper speech models download automatically the first time you transcribe.`
- Running from source: after `setup_venv.bat` add `:: setup_venv also runs scripts\fetch_diarization_weights.py, which needs a Hugging Face token ONCE (developers only; set HF_TOKEN). End users never need one.`
- Storage: `AI-provider API keys + HF token` → `AI-provider API keys`.
- Troubleshooting: replace the "HuggingFace 403 / cannot download diarization model" entry with `- **"Speaker-diarization model files are missing"** — the installation is incomplete; reinstall. In a development checkout run \`python scripts\fetch_diarization_weights.py\`.`

- [ ] **Step 4: Full gate**

```
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m bandit -q -r app -ll
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -m "not gui" -q
```
All clean/green. `git status --short` shows nothing under `models/`.

- [ ] **Step 5: Commit and hand back**

```
git add build.bat CampaignScribe.spec setup_venv.bat PRIVACY.md README.md tests
git commit -m "build: fetch and bundle diarization weights, notices and PRIVACY.md; docs drop the HuggingFace token"
```
Report commits and counts. The controller runs the manual checks on Mike's PC: `run_dev.bat` transcription of a test clip; `build.bat`, then the packaged exe on the same clip with `%USERPROFILE%\.cache\huggingface\hub\models--pyannote--speaker-diarization-community-1` temporarily renamed (and renamed back after). PR body: `Roadmap: Imagination-Industries-LLC/CampaignScribe-planning#11`.
