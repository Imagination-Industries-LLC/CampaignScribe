# Phase 0 — Engineering Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up CampaignScribe's engineering foundation — repo tooling, a real pytest suite covering the existing robustness code, GitHub Actions CI gates, PR-bot AI reviewers, and a descriptive-name tab refactor — so every future PR is automatically linted, type-checked, security-scanned, tested, and AI-reviewed before merge.

**Architecture:** Configuration lives in `pyproject.toml` (ruff, mypy, pytest) + `requirements-dev.txt` (light test/lint deps only — no torch/whisperx). Tests live under `tests/` split into `unit/`, `integration/`, `smoke/`, with shared fixtures in `tests/conftest.py` that isolate `%APPDATA%`, swap in an in-memory keyring, and fake the Anthropic client. CI is two jobs (`ubuntu-latest` for lint/type/security/logic-tests, `windows-latest` for GUI + keyring tests). The tab rename is a pure mechanical refactor guarded by the new smoke test.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, bandit, semgrep, pip-audit, CodeQL, GitHub Actions, pre-commit. App stack (Tkinter/WhisperX/pyannote/anthropic) is unchanged.

**Target repo:** `Imagination-Industries-Inc/CampaignScribe` (public). Local clone: `H:\git\CampaignScribe`, `origin` → org repo, `personal` → archived old repo.

---

## Scope & sequencing

Phase 0 has five task groups. Execute in this order — each builds on the last:

- **Group A — Repo tooling foundation** (pyproject, dev deps, pre-commit, baseline ruff-clean).
- **Group B — Test suite** (TDD per module; the suite must exist before CI can run it).
- **Group C — CI workflows + branch protection** (wires Group B into Actions).
- **Group D — PR-bot AI reviewers** (CodeRabbit, Copilot, Qodo, Greptile — mostly GitHub UI / app installs).
- **Group E — Tab rename refactor** (guarded by the Group B smoke test; lands via a PR that exercises the full gauntlet).

**Execution branch:** do all work on a feature branch (e.g. `phase-0-foundation`), not `main`. Group E should go through its own PR so the new CI + AI reviewers run against it as a live demonstration.

### Explicitly deferred (NOT in Phase 0)
- **Release automation** (`release.yml`, Azure signing) — deferred to the Distribution phase (Phase 5) per the roadmap; the CI/CD spec's release half is out of scope here.
- **Cost-estimate unit test** — there is **no cost helper in the codebase** (`grep -i cost app/` returns nothing). Cost Transparency is spec #14 (Phase 2). Defer this test until #14 lands.
- **Scrubber / mailto-builder tests** — those features (#2 diagnostics, #10 feedback) don't exist yet (Phase 1). Defer.
- **`Safety`** (Layer 2) — optional/overlaps `pip-audit`; skip for now (pip-audit + CodeQL + bandit + semgrep is the required set).

### Notes on TDD framing for this phase
Most Group B tests are **characterization tests** over already-shipped, hardened code — they should pass on first run against current `app/`. Where a test is expected to pass immediately, the step says so. Genuine red→green TDD applies only where we add/repair code (none expected in Group B; Group E is a mechanical refactor verified by the smoke test). If a characterization test unexpectedly **fails**, stop and treat it as a real bug found — do not "fix" the test to match buggy behavior without confirming the behavior is correct.

---

## File Structure

**Created:**
- `pyproject.toml` — ruff + mypy + pytest config, project metadata.
- `requirements-dev.txt` — light test/lint deps (pytest, anthropic, httpx, keyring, python-docx, ruff, mypy, bandit, semgrep, pip-audit, pre-commit).
- `.pre-commit-config.yaml` — ruff lint+format hooks.
- `tests/__init__.py`, `tests/conftest.py` — shared fixtures.
- `tests/unit/test_config.py`, `test_speakers_io.py`, `test_db.py`, `test_claude_api.py`, `test_speaker_id.py`, `test_summarizer.py`.
- `tests/integration/test_pipeline.py`.
- `tests/smoke/test_app_smoke.py`.
- `.github/workflows/ci.yml` — lint/type/security/test gates.
- `.github/dependabot.yml` — weekly dependency PRs.
- `.coderabbit.yaml` — CodeRabbit config.
- `docs/CONTRIBUTING.md` — references the gauntlet (optional but cheap; reviewers look for it).

**Modified (Group E rename):**
- `app/ui/tab1_onboard.py` → `app/ui/discover_tab.py` (`Tab1Onboard` → `DiscoverTab`)
- `app/ui/tab3_manage.py` → `app/ui/build_profile_tab.py` (`Tab3Manage` → `BuildProfileTab`)
- `app/ui/tab5_transcribe.py` → `app/ui/transcribe_tab.py` (`Tab5Transcribe` → `TranscribeTab`)
- `app/ui/tab6_summarize.py` → `app/ui/summarize_tab.py` (`Tab6Summarize` → `SummarizeTab`)
- `app/ui/tab2_refine.py` → `app/ui/refine_tab.py` (`Tab2Refine` → `RefineTab`)
- `app/ui/tab4_history.py` → `app/ui/history_tab.py` (`Tab4History` → `HistoryTab`)
- `app/ui/app_window.py` — imports, `self.tabN` attributes, `_tab_specs`, `open_settings` loop.

**Modified (stale-repo cleanup):**
- `README.md` and `app/ui/app_window.py:436` — `github.com/MikeRompel/CampaignScribe` → `github.com/Imagination-Industries-Inc/CampaignScribe`.

---

# Group A — Repo tooling foundation

### Task A1: `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "campaignscribe"
version = "0.0.0"
description = "Windows desktop app for transcribing and summarizing tabletop RPG sessions"
requires-python = ">=3.11"

[tool.ruff]
target-version = "py311"
line-length = 100
extend-exclude = ["build", "dist", "build_workspace", ".venv"]

[tool.ruff.lint]
# Start conservative: pyflakes (F), pycodestyle errors (E), warnings (W),
# isort (I), pyupgrade (UP), bugbear (B). Tighten over time.
select = ["E", "F", "W", "I", "UP", "B"]
# E501 line-too-long is handled by the formatter; ignore the linter copy.
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
# Gradual mode: non-blocking. The codebase is not fully typed yet.
ignore_missing_imports = true
warn_unused_ignores = false
warn_return_any = false
check_untyped_defs = false
exclude = ["build/", "dist/", "build_workspace/", "tests/"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "gui: tests that construct Tk windows (run on windows-latest / a display)",
]
addopts = "-ra"
```

- [ ] **Step 2: Verify ruff reads the config**

Run: `.venv\Scripts\python -m ruff check --show-settings . 2>$null | Select-String "line-length"`
Expected: shows `line-length = 100` (config is parsed; exact output format may vary by ruff version — any non-error is fine).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyproject.toml with ruff/mypy/pytest config"
```

---

### Task A2: `requirements-dev.txt`

**Files:**
- Create: `requirements-dev.txt`

**Rationale:** CI installs ONLY these light deps for the test/lint jobs — never the 4.7 GB ML stack. All heavy paths (torch/whisperx/pyannote/diarization) are mocked in tests. `anthropic`, `httpx`, `keyring`, `python-docx` are needed because `claude_api`/`summarizer` import them lazily and some tests exercise that code directly.

- [ ] **Step 1: Write `requirements-dev.txt`**

```
# Test + lint tooling (light; NO torch/whisperx/pyannote — those are mocked in tests)
pytest>=8.0
anthropic>=0.40
httpx>=0.27
keyring>=24.0
python-docx>=1.1
ruff>=0.6
mypy>=1.11
bandit>=1.7
semgrep>=1.80
pip-audit>=2.7
pre-commit>=3.7
```

- [ ] **Step 2: Install into the dev venv**

Run: `.venv\Scripts\python -m pip install -r requirements-dev.txt`
Expected: all install successfully.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "build: add requirements-dev.txt (light test/lint deps)"
```

---

### Task A3: `.pre-commit-config.yaml`

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 2: Install the hook locally (optional, local-only)**

Run: `.venv\Scripts\python -m pre_commit install`
Expected: `pre-commit installed at .git\hooks\pre-commit`

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "build: add pre-commit ruff hooks"
```

---

### Task A4: Make the existing codebase ruff-clean (baseline green)

**Files:**
- Modify: any `app/**.py` / `main.py` flagged by ruff.

- [ ] **Step 1: Run the formatter**

Run: `.venv\Scripts\python -m ruff format .`
Expected: reports N files reformatted.

- [ ] **Step 2: Run the linter with autofix**

Run: `.venv\Scripts\python -m ruff check --fix .`
Expected: most issues auto-fixed; a short list may remain.

- [ ] **Step 3: Manually resolve remaining lint findings**

Review each remaining finding. Typical leftovers: unused imports (remove), bare `except` (leave if intentional + add `# noqa: E722` with a reason), `B008`/`B006` mutable defaults (fix only if genuinely buggy). Do NOT silence findings wholesale — fix or justify each.

- [ ] **Step 4: Verify clean**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: `All checks passed!` and no formatting diff.

- [ ] **Step 5: Sanity-run the app from source (no regressions)**

Run: `H:\git\CampaignScribe\run_dev.bat` — confirm the window opens and tabs render, then close it.
Expected: app launches normally (formatting/lint fixes didn't break imports).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "style: apply ruff format + lint fixes to existing code"
```

---

# Group B — Test suite

### Task B1: `tests/conftest.py` + package markers

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/smoke/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create the empty package files**

Create each `__init__.py` listed above as an empty file.

- [ ] **Step 2: Write `tests/conftest.py`**

```python
"""Shared fixtures.

Isolation strategy:
- ``isolate_appdata`` (autouse) points %APPDATA% (and HOME) at a tmp dir so
  config.json / data.db / errors.log never touch the real user profile.
- ``mem_keyring`` (autouse) installs an in-memory keyring backend so
  save/get_anthropic_key work deterministically without the OS credential store.
- ``fake_claude`` swaps app.core.claude_api.make_client for a fake whose
  messages.create() returns queued canned text — no network, no real key.
"""
from __future__ import annotations

import keyring
from keyring.backend import KeyringBackend
import pytest


# ---- in-memory keyring backend ----
class _InMemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self):
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def mem_keyring():
    prev = keyring.get_keyring()
    keyring.set_keyring(_InMemoryKeyring())
    yield
    keyring.set_keyring(prev)


@pytest.fixture(autouse=True)
def isolate_appdata(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return appdata


# ---- fake Anthropic client ----
class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.calls.append(kwargs)
        if not self._parent.responses:
            raise AssertionError("FakeClient.messages.create called with no queued response")
        return _FakeMessage(self._parent.responses.pop(0))


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = _FakeMessages(self)


@pytest.fixture
def fake_claude(monkeypatch):
    """Returns a factory: call ``fake_claude(["resp1", "resp2"])`` to install a
    FakeClient and get it back for assertions on ``.calls``."""
    def _install(responses):
        client = FakeClient(responses)
        monkeypatch.setattr("app.core.claude_api.make_client", lambda api_key: client)
        return client
    return _install
```

- [ ] **Step 3: Verify pytest collects with zero tests**

Run: `.venv\Scripts\python -m pytest -q`
Expected: `no tests ran` (collection succeeds, fixtures import cleanly).

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add pytest scaffolding + isolation/keyring/anthropic fixtures"
```

---

### Task B2: `tests/unit/test_config.py`

**Files:**
- Test: `tests/unit/test_config.py`
- Under test: `app/config.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for app.config: atomic save, key allowlist, corrupt-file fallback, secrets."""
from __future__ import annotations

import json

from app import config


def test_save_config_is_atomic_and_leaves_no_tmp():
    config.save_config({"default_num_speakers": 7})
    p = config.get_config_path()
    assert p.exists()
    assert not p.with_suffix(p.suffix + ".tmp").exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["default_num_speakers"] == 7


def test_save_config_drops_unknown_keys():
    config.save_config({"default_num_speakers": 3, "evil_key": "x"})
    data = json.loads(config.get_config_path().read_text(encoding="utf-8"))
    assert "evil_key" not in data
    # every persisted key is in the known schema
    assert set(data).issubset(set(config.DEFAULT_CONFIG))


def test_save_config_fills_missing_keys_with_defaults():
    config.save_config({})  # nothing provided
    data = json.loads(config.get_config_path().read_text(encoding="utf-8"))
    assert data["default_whisper_model"] == config.DEFAULT_CONFIG["default_whisper_model"]


def test_load_config_returns_defaults_when_missing():
    assert not config.get_config_path().exists()
    cfg = config.load_config()
    assert cfg["default_num_speakers"] == config.DEFAULT_CONFIG["default_num_speakers"]
    # load_config creates the file when absent
    assert config.get_config_path().exists()


def test_load_config_recovers_from_corrupt_file():
    config.get_config_path().write_text("{ this is not json", encoding="utf-8")
    cfg = config.load_config()
    assert cfg == dict(config.DEFAULT_CONFIG)


def test_load_config_merges_and_ignores_unknown_keys():
    config.get_config_path().write_text(
        json.dumps({"default_num_speakers": 9, "bogus": 1}), encoding="utf-8"
    )
    cfg = config.load_config()
    assert cfg["default_num_speakers"] == 9
    assert "bogus" not in cfg


def test_set_and_get_last_dir(tmp_path):
    f = tmp_path / "audio" / "sess.wav"
    f.parent.mkdir(parents=True)
    f.write_text("x")
    config.set_last_dir("audio", str(f))
    assert config.get_last_dir("audio") == str(f.parent)


def test_anthropic_key_roundtrip_via_keyring():
    assert config.get_anthropic_key() == ""
    config.save_anthropic_key("sk-test-123")
    assert config.get_anthropic_key() == "sk-test-123"
```

- [ ] **Step 2: Run — expect PASS (characterization of existing code)**

Run: `.venv\Scripts\python -m pytest tests/unit/test_config.py -v`
Expected: all PASS. If any fails, stop and investigate as a possible real bug.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_config.py
git commit -m "test: cover config atomic save, allowlist, corrupt-fallback, keyring"
```

---

### Task B3: `tests/unit/test_speakers_io.py`

**Files:**
- Test: `tests/unit/test_speakers_io.py`
- Under test: `app/core/speakers_io.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for app.core.speakers_io: atomic save + .bak, load validation, transform."""
from __future__ import annotations

import json

import pytest

from app.core import speakers_io


def test_save_speakers_json_atomic_no_tmp(tmp_path):
    p = tmp_path / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "Curse of Strahd"})
    assert p.exists()
    assert not p.with_suffix(".json.tmp").exists()
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_save_speakers_json_creates_bak_on_overwrite(tmp_path):
    p = tmp_path / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "v1"})
    speakers_io.save_speakers_json(str(p), {"campaign": "v2"})
    bak = p.with_suffix(".json.bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8"))["campaign"] == "v1"
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "v2"


def test_save_speakers_json_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "deep" / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "x"})
    assert p.exists()


def test_load_speakers_json_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        speakers_io.load_speakers_json(str(tmp_path / "nope.json"))


def test_load_speakers_json_non_dict_raises(tmp_path):
    p = tmp_path / "speakers.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        speakers_io.load_speakers_json(str(p))


def test_load_speakers_json_fills_defaults(tmp_path):
    p = tmp_path / "speakers.json"
    p.write_text("{}", encoding="utf-8")
    data = speakers_io.load_speakers_json(str(p))
    assert data["players"] == []
    assert data["known_non_players"] == []
    assert "unknown_speaker_label" in data["fallback_policy"]


def test_profiles_to_speakers_doc_routes_players_and_non_players():
    speakers = [
        {"display_name": "Mike", "role": "Player", "character_name": "Wellbrix",
         "include_in_tracking": 1, "source_speaker_id": "SPEAKER_01"},
        {"display_name": "DM Josh", "role": "Non-Player",
         "include_in_tracking": 1, "source_speaker_id": "SPEAKER_00"},
        {"display_name": "Background", "role": "Player",
         "include_in_tracking": 0, "source_speaker_id": "SPEAKER_09"},
    ]
    doc = speakers_io.profiles_to_speakers_doc("Camp", "ctx", speakers)
    player_names = [p["player_name"] for p in doc["players"]]
    np_names = [n["name"] for n in doc["known_non_players"]]
    assert "Mike" in player_names
    assert "DM Josh" in np_names           # Non-Player role -> known_non_players
    assert "Background" in np_names         # not included -> known_non_players
    # excluded speaker is flagged as "ignore"
    bg = next(n for n in doc["known_non_players"] if n["name"] == "Background")
    assert bg["role"] == "ignore"
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/unit/test_speakers_io.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_speakers_io.py
git commit -m "test: cover speakers_io atomic save/.bak, load validation, transform"
```

---

### Task B4: `tests/unit/test_db.py`

**Files:**
- Test: `tests/unit/test_db.py`
- Under test: `app/data/db.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for app.data.db: schema/version, column allowlist, CRUD, cascade, JSON fields."""
from __future__ import annotations

import sqlite3

import pytest

from app.data import db


def test_init_db_sets_user_version_to_baseline():
    db.init_db()
    with db.get_conn() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
    assert version == db.SCHEMA_BASELINE


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()  # second call must not raise
    with db.get_conn() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_BASELINE


def test_get_conn_enables_foreign_keys():
    db.init_db()
    with db.get_conn() as c:
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_update_session_rejects_unknown_column():
    db.init_db()
    sid = db.create_session("Test")
    with pytest.raises(ValueError):
        db.update_session(sid, status="done; DROP TABLE sessions")  # not in allowlist


def test_update_session_accepts_allowlisted_column():
    db.init_db()
    sid = db.create_session("Test")
    db.update_session(sid, status="complete")
    assert db.get_session(sid)["status"] == "complete"


def test_update_speaker_profile_rejects_unknown_column():
    db.init_db()
    sid = db.create_session("Test")
    pid = db.add_speaker_profile(sid, {"display_name": "Mike"})
    with pytest.raises(ValueError):
        db.update_speaker_profile(pid, bogus_col="x")


def test_speaker_profile_json_fields_roundtrip():
    db.init_db()
    sid = db.create_session("Test")
    pid = db.add_speaker_profile(sid, {
        "display_name": "Mike",
        "speech_patterns": ["says 'huzzah'"],
        "sample_quotes": ["I attack!"],
    })
    rows = db.get_speakers_for_session(sid)
    row = next(r for r in rows if r["id"] == pid)
    assert row["speech_patterns"] == ["says 'huzzah'"]
    assert row["sample_quotes"] == ["I attack!"]


def test_delete_session_cascades_to_profiles():
    db.init_db()
    sid = db.create_session("Test")
    db.add_speaker_profile(sid, {"display_name": "Mike"})
    db.delete_session(sid)
    assert db.get_speakers_for_session(sid) == []


def test_list_sessions_search_filters():
    db.init_db()
    db.create_session("Strahd Recap", campaign_name="Curse of Strahd")
    db.create_session("Other", campaign_name="Different")
    results = db.list_sessions(search="Strahd")
    assert any("Strahd" in r["display_name"] for r in results)
    assert all("Strahd" in r["display_name"] or "Strahd" in (r["campaign_name"] or "")
               for r in results)
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/unit/test_db.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_db.py
git commit -m "test: cover db schema/version, column allowlist, CRUD, cascade, JSON fields"
```

---

### Task B5: `tests/unit/test_claude_api.py`

**Files:**
- Test: `tests/unit/test_claude_api.py`
- Under test: `app/core/claude_api.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for app.core.claude_api.make_client: empty-key guard + timeout/retry config."""
from __future__ import annotations

import pytest

from app.core import claude_api


def test_make_client_raises_on_empty_key():
    with pytest.raises(RuntimeError):
        claude_api.make_client("")


def test_make_client_configures_timeout_and_retries(monkeypatch):
    captured = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)

    client = claude_api.make_client("sk-test")
    assert isinstance(client, _FakeAnthropic)
    assert captured["api_key"] == "sk-test"
    assert captured["max_retries"] == claude_api._MAX_RETRIES
    # timeout is an httpx.Timeout; connect should match the configured connect budget
    assert captured["timeout"].connect == claude_api._TIMEOUT_CONNECT
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/unit/test_claude_api.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_claude_api.py
git commit -m "test: cover claude_api make_client guard + timeout/retry config"
```

---

### Task B6: `tests/unit/test_speaker_id.py`

**Files:**
- Test: `tests/unit/test_speaker_id.py`
- Under test: `app/core/speaker_id.py` (`_extract_json_object`, `format_segments_to_text`)

- [ ] **Step 1: Write the tests**

```python
"""Tests for speaker_id._extract_json_object edge cases + format_segments_to_text."""
from __future__ import annotations

import pytest

from app.core import speaker_id


def test_extract_plain_json_object():
    assert speaker_id._extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_array():
    assert speaker_id._extract_json_object('[1, 2, 3]') == [1, 2, 3]


def test_extract_fenced_json():
    text = '```json\n{"a": 1, "b": 2}\n```'
    assert speaker_id._extract_json_object(text) == {"a": 1, "b": 2}


def test_extract_fenced_json_no_lang():
    text = '```\n{"a": 1}\n```'
    assert speaker_id._extract_json_object(text) == {"a": 1}


def test_extract_json_with_leading_prose():
    text = 'Here is your result:\n{"SPEAKER_00": "DM"}'
    assert speaker_id._extract_json_object(text) == {"SPEAKER_00": "DM"}


def test_extract_json_ignores_trailing_explanation():
    text = '{"a": 1}\n\nHope that helps! Let me know if you need anything else.'
    assert speaker_id._extract_json_object(text) == {"a": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        speaker_id._extract_json_object("no json here at all")


def test_format_segments_collapses_consecutive_same_speaker():
    segments = [
        {"speaker": "SPEAKER_00", "text": "Hello"},
        {"speaker": "SPEAKER_00", "text": "there"},
        {"speaker": "SPEAKER_01", "text": "Hi"},
    ]
    out = speaker_id.format_segments_to_text(segments, {})
    assert out == "SPEAKER_00: Hello there\n\nSPEAKER_01: Hi"


def test_format_segments_applies_mapping_and_skips():
    segments = [
        {"speaker": "SPEAKER_00", "text": "Narration"},
        {"speaker": "SPEAKER_02", "text": "background noise"},
        {"speaker": "SPEAKER_01", "text": "I attack"},
    ]
    out = speaker_id.format_segments_to_text(
        segments,
        {"SPEAKER_00": "DM", "SPEAKER_01": "Mike"},
        skip_speakers=["SPEAKER_02"],
    )
    assert "DM: Narration" in out
    assert "Mike: I attack" in out
    assert "background noise" not in out


def test_format_segments_skips_empty_text():
    segments = [
        {"speaker": "SPEAKER_00", "text": ""},
        {"speaker": "SPEAKER_00", "text": "real line"},
    ]
    out = speaker_id.format_segments_to_text(segments, {})
    assert out == "SPEAKER_00: real line"
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/unit/test_speaker_id.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_speaker_id.py
git commit -m "test: cover _extract_json_object edge cases + format_segments_to_text"
```

---

### Task B7: `tests/unit/test_summarizer.py`

**Files:**
- Test: `tests/unit/test_summarizer.py`
- Under test: `app/core/summarizer.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for summarizer helpers + consolidate_summaries (mocked client) + docx export."""
from __future__ import annotations

from app.core import summarizer


def test_safe_filename_strips_invalid_and_spaces():
    assert summarizer.safe_filename("Session 1: The Crypt!") == "Session_1_The_Crypt"


def test_safe_filename_empty_falls_back():
    assert summarizer.safe_filename("***") == "Session_Summary"


def test_parse_session_name_found():
    text = "SESSION NAME: The Sunless Citadel\n\nThings happened."
    assert summarizer.parse_session_name_from_text(text) == "The Sunless Citadel"


def test_parse_session_name_absent():
    assert summarizer.parse_session_name_from_text("no header here") is None


def test_consolidate_summaries_parses_name_and_body(fake_claude):
    fake_claude(["SESSION NAME: Into the Mist\n\n## Recap\nThe party fled."])
    result = summarizer.consolidate_summaries(
        ["part 1 summary"], {"campaign": "Strahd"}, api_key="sk-x"
    )
    assert result["session_name"] == "Into the Mist"
    assert "The party fled." in result["body"]
    assert result["raw"].startswith("SESSION NAME:")


def test_consolidate_summaries_defaults_name_when_missing(fake_claude):
    fake_claude(["No name header, just prose."])
    result = summarizer.consolidate_summaries(["p1"], {}, api_key="sk-x")
    assert result["session_name"] == "Session Summary"


def test_write_docx_creates_file(tmp_path):
    out = tmp_path / "out" / "summary.docx"
    summarizer.write_docx(
        str(out),
        session_name="Test Session",
        consolidated_body="## Recap\n- point one\n- point two\n\nKEY EVENTS\nStuff.",
        part_summaries=["Part one text"],
        campaign_name="Strahd",
    )
    assert out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/unit/test_summarizer.py -v`
Expected: all PASS (requires `python-docx` from requirements-dev.txt).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_summarizer.py
git commit -m "test: cover summarizer helpers, consolidate parsing, docx export"
```

---

### Task B8: `tests/integration/test_pipeline.py`

**Files:**
- Test: `tests/integration/test_pipeline.py`
- Under test: `speaker_id.identify_speakers` + `format_segments_to_text` + `summarizer.summarize_part` + `consolidate_summaries`, with the LLM mocked and diarization sample-collection mocked.

- [ ] **Step 1: Write the tests**

```python
"""Integration: identify -> format -> summarize -> consolidate with mocked LLM + diarization."""
from __future__ import annotations

from app.core import speaker_id, summarizer

SEGMENTS = [
    {"speaker": "SPEAKER_00", "text": "Roll me a perception check."},
    {"speaker": "SPEAKER_01", "text": "I rolled a 17."},
    {"speaker": "SPEAKER_00", "text": "You spot a hidden door."},
]

SPEAKERS_REF = {
    "campaign": "Curse of Strahd",
    "context": "Gothic horror",
    "players": [{"player_name": "Mike", "character_name": "Wellbrix"}],
}


def test_identify_then_format(monkeypatch, fake_claude):
    # Mock diarization sample collection so no audio/ML is needed.
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"], "SPEAKER_01": ["b"]},
    )
    fake_claude(['{"SPEAKER_00": "Josh (DM)", "SPEAKER_01": "Mike (Wellbrix)"}'])

    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, api_key="sk-x")
    assert mapping["SPEAKER_00"] == "Josh (DM)"

    transcript = speaker_id.format_segments_to_text(SEGMENTS, mapping)
    assert "Josh (DM): Roll me a perception check." in transcript
    assert "Mike (Wellbrix): I rolled a 17." in transcript


def test_identify_falls_back_on_bad_llm_json(monkeypatch, fake_claude):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"]},
    )
    fake_claude(["the model rambled and returned no json"])
    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, api_key="sk-x")
    # Fallback: each detected speaker maps to itself.
    assert mapping == {"SPEAKER_00": "SPEAKER_00"}


def test_summarize_then_consolidate(fake_claude):
    client = fake_claude([
        "## Part 1\nThe party entered the crypt.",          # summarize_part
        "SESSION NAME: The Crypt\n\n## Recap\nAll survived.",  # consolidate
    ])
    transcript = "DM: You enter a crypt.\n\nMike: I draw my sword."
    part = summarizer.summarize_part(transcript, SPEAKERS_REF, "Summarize this.", "sk-x", 1)
    assert "crypt" in part.lower()

    result = summarizer.consolidate_summaries([part], SPEAKERS_REF, api_key="sk-x")
    assert result["session_name"] == "The Crypt"
    # both LLM calls happened
    assert len(client.calls) == 2
```

- [ ] **Step 2: Run — expect PASS**

Run: `.venv\Scripts\python -m pytest tests/integration/test_pipeline.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pipeline.py
git commit -m "test: integration pipeline (identify/format/summarize/consolidate) with mocks"
```

---

### Task B9: `tests/smoke/test_app_smoke.py`

**Files:**
- Test: `tests/smoke/test_app_smoke.py`
- Under test: `app/ui/app_window.py` (`AppWindow` constructs headless; all 6 tabs build; `_tab_specs` order; `on_show` doesn't throw).

**Note:** This test both protects the Group E rename AND verifies headless construction. It is marked `@pytest.mark.gui`; CI runs it on `windows-latest`. Locally on a machine with no display it self-skips on `TclError`.

- [ ] **Step 1: Write the test**

```python
"""Headless smoke test: AppWindow constructs, all tabs build, tab order is correct."""
from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui

# Expected display labels in display order. Update ONLY if the intended tab
# ordering changes — names are decoupled from module/class names by Group E.
EXPECTED_LABELS = [
    "1. Discover",
    "2. Build Profile",
    "3. Transcribe",
    "4. Summarize",
    "5. Refine",
    "6. History",
]


@pytest.fixture
def app(monkeypatch):
    # Avoid importing torch / probing GPU during construction.
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None,
                 "error": "stubbed in test", "smi_gpu_name": None},
    )
    try:
        from app.ui.app_window import AppWindow
        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display available for Tk: {e}")
    win.withdraw()
    win.update_idletasks()
    yield win
    win.destroy()


def test_app_window_constructs_with_six_tabs(app):
    assert len(app.notebook.tabs()) == 6


def test_tab_labels_in_expected_order(app):
    labels = [app.notebook.tab(i, "text") for i in range(len(app.notebook.tabs()))]
    assert labels == EXPECTED_LABELS


def test_each_tab_is_a_frame_widget(app):
    for widget, _label, _icon in app._tab_specs:
        assert widget.winfo_exists()


def test_on_tab_changed_does_not_raise(app):
    # Selecting each tab fires <<NotebookTabChanged>> -> on_show hooks.
    for i in range(len(app.notebook.tabs())):
        app.notebook.select(i)
        app.update_idletasks()
```

- [ ] **Step 2: Run — expect PASS (on Windows / a display)**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_app_smoke.py -v`
Expected: all PASS (or SKIP if no display).

- [ ] **Step 3: Run the full suite green**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all PASS/SKIP, zero failures.

- [ ] **Step 4: Commit**

```bash
git add tests/smoke/test_app_smoke.py
git commit -m "test: headless AppWindow smoke test (6 tabs, label order, on_show)"
```

---

# Group C — CI workflows + branch protection

### Task C1: `.github/workflows/ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

**Design:** Two jobs. `lint-test-linux` (ubuntu) runs ruff, mypy (non-blocking), bandit, semgrep, pip-audit, and the non-gui pytest. `gui-test-windows` (windows) runs the full suite including `@pytest.mark.gui`. Concurrency cancels superseded runs; pip is cached.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint-test-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dev deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      - name: Ruff lint
        run: ruff check .
      - name: Ruff format check
        run: ruff format --check .
      - name: Mypy (non-blocking)
        run: mypy app || true
      - name: Bandit (security)
        run: bandit -r app -ll
      - name: Semgrep (OWASP/SAST)
        run: semgrep --config=p/python --config=p/owasp-top-ten --error app
      - name: pip-audit (deps)
        run: pip-audit -r requirements-dev.txt
      - name: Pytest (non-gui)
        run: pytest -m "not gui" -v

  gui-test-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dev deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      - name: Pytest (full incl. gui)
        run: pytest -v
```

- [ ] **Step 2: Validate YAML locally**

Run: `.venv\Scripts\python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit and push the branch to trigger CI**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions ruff/mypy/bandit/semgrep/pip-audit/pytest workflow"
git push -u origin phase-0-foundation
```

- [ ] **Step 4: Verify CI runs green**

Run: `gh run list --branch phase-0-foundation --limit 1` then `gh run watch <run-id>`
Expected: both jobs succeed. If bandit/semgrep flag real issues, triage them (fix or add a justified inline suppression) — do not blanket-disable.

---

### Task C2: Enable CodeQL (default setup)

**Files:** none (GitHub-managed) — OR `.github/workflows/codeql.yml` if advanced setup is needed.

- [ ] **Step 1: Enable CodeQL default setup (preferred — zero YAML)**

In the GitHub UI: **Settings → Code security and analysis → CodeQL analysis → Set up → Default**. Language: Python. Enable.
(Default setup is free for public repos and auto-updates; advanced YAML is only needed for custom build steps, which this pure-Python repo does not have.)

- [ ] **Step 2: Verify**

Run: `gh api repos/Imagination-Industries-Inc/CampaignScribe/code-scanning/default-setup`
Expected: `"state": "configured"`.

---

### Task C3: `.github/dependabot.yml`

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Write `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
```

- [ ] **Step 2: Commit**

```bash
git add .github/dependabot.yml
git commit -m "ci: enable Dependabot for pip + github-actions"
```

---

### Task C4: Branch protection on `main`

**Files:** none (GitHub API).

**Prereq:** Group C1 CI has run at least once so the check contexts (`lint-test-linux`, `gui-test-windows`) are known to GitHub. Requires repo-admin (the org owner).

- [ ] **Step 1: Apply branch protection requiring green CI + PR review**

Run (PowerShell — write the JSON to a temp file to avoid quoting issues):
```powershell
$body = @'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint-test-linux", "gui-test-windows"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null
}
'@
[System.IO.File]::WriteAllText("$env:TEMP\bp.json", $body, [System.Text.UTF8Encoding]::new($false))
gh api -X PUT repos/Imagination-Industries-Inc/CampaignScribe/branches/main/protection `
  -H "Accept: application/vnd.github+json" --input "$env:TEMP\bp.json"
```
Expected: returns the protection JSON (HTTP 200). Note: `required_approving_review_count: 0` lets the solo owner merge once checks + AI reviews are green; raise it later if collaborators join.

- [ ] **Step 2: Verify**

Run: `gh api repos/Imagination-Industries-Inc/CampaignScribe/branches/main/protection --jq '.required_status_checks.contexts'`
Expected: `["lint-test-linux","gui-test-windows"]`

---

# Group D — PR-bot AI reviewers

These are GitHub App installations + light config. They cannot be fully done from the CLI; each step says what the user must click. Install each app **scoped to `Imagination-Industries-Inc/CampaignScribe`**.

### Task D1: CodeRabbit

**Files:**
- Create: `.coderabbit.yaml`

- [ ] **Step 1: Write `.coderabbit.yaml`**

```yaml
# CodeRabbit configuration. Free for public repositories.
language: en
reviews:
  profile: chill
  request_changes_workflow: false
  high_level_summary: true
  poem: false
  auto_review:
    enabled: true
    drafts: false
chat:
  auto_reply: true
```

- [ ] **Step 2: Commit**

```bash
git add .coderabbit.yaml
git commit -m "ci: add CodeRabbit config"
```

- [ ] **Step 3: Install the app (user action)**

Go to https://github.com/apps/coderabbitai → **Install** → select the `Imagination-Industries-Inc` org → restrict to the `CampaignScribe` repo. CodeRabbit will auto-review new PRs.

---

### Task D2: GitHub Copilot code review

**Files:** none (repo ruleset / UI).

- [ ] **Step 1: Enable Copilot as an automatic reviewer (user action)**

Requires a Copilot subscription that includes code review. In **Settings → Rules → Rulesets → New branch ruleset** targeting `main`, add **"Require Copilot code review"** (or add `@copilot` as a default reviewer via Settings → Collaborators and teams → default reviewers, depending on plan). Verify it comments on the next PR.

- [ ] **Step 2: Verify on a PR**

Open/refresh the Group E PR and confirm a Copilot review appears. If the plan doesn't expose auto-review, request it manually via the PR "Reviewers → Copilot" control.

---

### Task D3: Qodo (formerly CodiumAI PR-Agent)

**Files:** optional `.pr_agent.toml` (defaults are fine to start).

- [ ] **Step 1: Install Qodo Merge (user action)**

Go to https://github.com/apps/qodo-merge-pro (or the open-source `pr-agent`) → **Install** → org `Imagination-Industries-Inc` → repo `CampaignScribe`. Free tier covers public/open-source repos.

- [ ] **Step 2: Verify**

On a PR, comment `/review` (if not automatic) and confirm Qodo responds. Enable auto-review in the Qodo dashboard if available.

---

### Task D4: Greptile

**Files:** none.

- [ ] **Step 1: Install Greptile (user action)**

Go to https://app.greptile.com → connect GitHub → authorize for `Imagination-Industries-Inc/CampaignScribe` → enable **automatic PR reviews**.

- [ ] **Step 2: Verify**

Confirm Greptile posts a review on the next PR.

- [ ] **Step 3: Record which reviewers are live**

Update `docs/CONTRIBUTING.md` (Task: create it if absent) listing the active reviewers and that all CI checks + AI reviews must be green/triaged before merge.

---

# Group E — Tab rename refactor

**Guard:** the Group B9 smoke test (`tests/smoke/test_app_smoke.py`) asserts the six tabs build and appear in the exact `EXPECTED_LABELS` order. Run it before and after to prove the rename is behavior-preserving.

**Mapping (module → new module; class → new class; unchanged display label):**

| Old module | Old class | New module | New class | Display label |
|---|---|---|---|---|
| `tab1_onboard.py` | `Tab1Onboard` | `discover_tab.py` | `DiscoverTab` | `1. Discover` |
| `tab3_manage.py` | `Tab3Manage` | `build_profile_tab.py` | `BuildProfileTab` | `2. Build Profile` |
| `tab5_transcribe.py` | `Tab5Transcribe` | `transcribe_tab.py` | `TranscribeTab` | `3. Transcribe` |
| `tab6_summarize.py` | `Tab6Summarize` | `summarize_tab.py` | `SummarizeTab` | `4. Summarize` |
| `tab2_refine.py` | `Tab2Refine` | `refine_tab.py` | `RefineTab` | `5. Refine` |
| `tab4_history.py` | `Tab4History` | `history_tab.py` | `HistoryTab` | `6. History` |

**Confirmed facts:** all six classes subclass `ttk.Frame` with `__init__(self, master, app_window)`; no tab module imports another tab module; only `app_window.py` imports them; the PyInstaller spec references `app.ui.app_window` (not individual tabs), so **no `.spec` change is needed**. Internal helper classes inside `build_profile_tab.py` (profile editor) and `summarize_tab.py` (prompt editor) keep their names.

### Task E1: Establish the pre-rename green baseline

- [ ] **Step 1: Run the smoke test and capture the passing label order**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_app_smoke.py -v`
Expected: PASS — this is the behavior we must preserve.

### Task E2: Rename module files (git-tracked moves)

- [ ] **Step 1: Move each file with `git mv`**

```bash
cd /h/git/CampaignScribe
git mv app/ui/tab1_onboard.py     app/ui/discover_tab.py
git mv app/ui/tab3_manage.py      app/ui/build_profile_tab.py
git mv app/ui/tab5_transcribe.py  app/ui/transcribe_tab.py
git mv app/ui/tab6_summarize.py   app/ui/summarize_tab.py
git mv app/ui/tab2_refine.py      app/ui/refine_tab.py
git mv app/ui/tab4_history.py     app/ui/history_tab.py
```

### Task E3: Rename the classes inside each moved file

- [ ] **Step 1: Update each class name**

In each moved file, rename the class on its `class TabNName(ttk.Frame):` line per the mapping table. Use Edit on each file:
- `discover_tab.py`: `class Tab1Onboard(ttk.Frame):` → `class DiscoverTab(ttk.Frame):`
- `build_profile_tab.py`: `class Tab3Manage(ttk.Frame):` → `class BuildProfileTab(ttk.Frame):`
- `transcribe_tab.py`: `class Tab5Transcribe(ttk.Frame):` → `class TranscribeTab(ttk.Frame):`
- `summarize_tab.py`: `class Tab6Summarize(ttk.Frame):` → `class SummarizeTab(ttk.Frame):`
- `refine_tab.py`: `class Tab2Refine(ttk.Frame):` → `class RefineTab(ttk.Frame):`
- `history_tab.py`: `class Tab4History(ttk.Frame):` → `class HistoryTab(ttk.Frame):`

- [ ] **Step 2: Check for any class self-references / docstrings mentioning old names**

Run: `git grep -nE "Tab[1-6](Onboard|Refine|Manage|History|Transcribe|Summarize)" app/`
Expected after edits: matches ONLY in `app/ui/app_window.py` (fixed next). If a moved file references its own old class name (e.g. in a docstring or a `super()`-adjacent comment), update it.

### Task E4: Update `app_window.py` imports, attributes, and `_tab_specs`

**Files:**
- Modify: `app/ui/app_window.py` (imports lines 15-20; tab construction lines 107-112; `_tab_specs` lines 115-122; `open_settings` loop lines 253-255)

- [ ] **Step 1: Replace the import block**

```python
from app.ui.discover_tab import DiscoverTab
from app.ui.refine_tab import RefineTab
from app.ui.build_profile_tab import BuildProfileTab
from app.ui.history_tab import HistoryTab
from app.ui.transcribe_tab import TranscribeTab
from app.ui.summarize_tab import SummarizeTab
```

- [ ] **Step 2: Replace the tab construction block (descriptive attribute names)**

```python
        self.discover_tab = DiscoverTab(self.notebook, self)
        self.refine_tab = RefineTab(self.notebook, self)
        self.build_profile_tab = BuildProfileTab(self.notebook, self)
        self.history_tab = HistoryTab(self.notebook, self)
        self.transcribe_tab = TranscribeTab(self.notebook, self)
        self.summarize_tab = SummarizeTab(self.notebook, self)
```

- [ ] **Step 3: Replace `_tab_specs` (display order unchanged)**

```python
        # (widget, label, icon-name) in display order
        self._tab_specs = [
            (self.discover_tab, "1. Discover", "discover"),
            (self.build_profile_tab, "2. Build Profile", "profile"),
            (self.transcribe_tab, "3. Transcribe", "transcribe"),
            (self.summarize_tab, "4. Summarize", "summarize"),
            (self.refine_tab, "5. Refine", "refine"),
            (self.history_tab, "6. History", "history"),
        ]
```

- [ ] **Step 4: Replace the `open_settings` fan-out loop**

```python
        for tab in (self.discover_tab, self.refine_tab, self.build_profile_tab,
                    self.history_tab, self.transcribe_tab, self.summarize_tab):
            if hasattr(tab, "on_settings_changed"):
                tab.on_settings_changed()
```

- [ ] **Step 5: Confirm no stale references remain anywhere**

Run: `git grep -nE "self\.tab[1-6]\b|Tab[1-6](Onboard|Refine|Manage|History|Transcribe|Summarize)|tab[1-6]_(onboard|refine|manage|history|transcribe|summarize)" .`
Expected: **no matches** (outside this plan doc). If `app_window.py` still references `self.tab1`/etc. elsewhere, update those too.

### Task E5: Verify the rename preserved behavior

- [ ] **Step 1: Ruff clean**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: clean.

- [ ] **Step 2: Smoke test still green (same labels, same order)**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_app_smoke.py -v`
Expected: PASS — `EXPECTED_LABELS` unchanged, so the rename is proven behavior-preserving.

- [ ] **Step 3: Full suite green**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all PASS/SKIP.

- [ ] **Step 4: Launch the app from source**

Run: `H:\git\CampaignScribe\run_dev.bat` — confirm all six tabs render in order and clicking each works; close.
Expected: identical behavior to before the rename.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename tab modules/classes to descriptive non-numeric names"
```

### Task E6: Stale-repo reference cleanup

**Files:**
- Modify: `app/ui/app_window.py:436` and `README.md`

- [ ] **Step 1: Update the About dialog URL**

In `app/ui/app_window.py`, change `github.com/MikeRompel/CampaignScribe` → `github.com/Imagination-Industries-Inc/CampaignScribe`.

- [ ] **Step 2: Update README repo references**

In `README.md`, replace any `MikeRompel/CampaignScribe` with `Imagination-Industries-Inc/CampaignScribe`.

- [ ] **Step 3: Verify none remain**

Run: `git grep -n "MikeRompel/CampaignScribe" .`
Expected: no matches (outside this plan doc).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: point repo references at the org repo"
```

---

# Final integration: PR through the full gauntlet

- [ ] **Step 1: Open the Phase 0 PR**

```bash
git push origin phase-0-foundation
gh pr create --repo Imagination-Industries-Inc/CampaignScribe --base main --head phase-0-foundation \
  --title "Phase 0: engineering foundation (CI, tests, AI reviewers, tab rename)" \
  --body "Stands up pyproject/ruff/mypy, the pytest suite, GitHub Actions CI, Dependabot, PR-bot reviewers, and the descriptive-name tab refactor. See docs/superpowers/plans/2026-05-28-phase-0-engineering-foundation.md."
```

- [ ] **Step 2: Confirm the gauntlet runs**

On the PR, verify: `lint-test-linux` + `gui-test-windows` CI jobs pass, CodeQL runs, and the AI reviewers (CodeRabbit, Copilot, Qodo, Greptile) post reviews.

- [ ] **Step 3: Triage AI-review findings**

Address or explicitly dismiss each finding (use the receiving-code-review skill for judgment — verify before implementing). Push fixes; re-confirm green.

- [ ] **Step 4: Merge once all checks are green and reviews triaged**

Merge via the PR (branch protection enforces required checks). Phase 0 complete → proceed to Phase 1.

---

## Self-Review (completed during planning)

- **Spec coverage — CI/CD spec:** ruff ✔ (C1), mypy gradual/non-blocking ✔ (A1+C1), pytest ✔ (B+C1), CodeQL ✔ (C2), pip-audit ✔ (C1), pre-commit ✔ (A3), pyproject tool config ✔ (A1), branch protection ✔ (C4), dependabot ✔ (C3). Release half (`release.yml`/signing) — **intentionally deferred** to Phase 5 per roadmap.
- **Spec coverage — QA/Gauntlet spec:** Layer 1 static (ruff/mypy/bandit/semgrep/CodeQL) ✔; Layer 2 deps (pip-audit + dependabot) ✔ (Safety deferred as redundant); Layer 3 tests (unit/integration/smoke) ✔; Layer 4 PR-bot AI reviewers (CodeRabbit/Copilot/Qodo/Greptile) ✔ (Group D); `/code-review ultra` + manual red-team + beta — **Phase 6**, out of scope. Adversarial parser cases ✔ (B6 `_extract_json_object`).
- **Spec coverage — roadmap Phase 0:** CI checks ✔, pytest suite ✔, PR-bot reviewers ✔, tab rename ✔.
- **Brief test targets:** atomic writes (B2/B3) ✔, DB migration + allowlists (B4) ✔, claude_api timeout/retry (B5) ✔, `_extract_json_object` (B6) ✔, smoke test (B9) ✔, integration mocks (B8) ✔. **Cost helpers — do not exist; deferred to #14/Phase 2 (documented).**
- **Type/name consistency:** fixture names (`fake_claude`, `isolate_appdata`, `mem_keyring`) used consistently; `EXPECTED_LABELS` is the single source of tab-order truth shared by B9 and Group E; rename mapping table matches the `_tab_specs` edit in E4.
- **Placeholders:** none — every test/config/command is concrete.
