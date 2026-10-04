# First-Run Setup Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guide a new user from first launch to a configured AI provider and a first campaign, and make the setup banner and empty Home actionable.

**Architecture:** A Tk-free `app/core/first_run.py` decides whether to offer setup (a one-time config flag plus `llm.provider_ready`). `AppWindow` runs startup prompts in sequence: the existing library import, then a new `WelcomeDialog` that hands off to `SettingsDialog(initial_provider=...)` and then offers a first campaign. `HomeTab` gains an empty state and a public `new_campaign()`.

**Tech Stack:** Python 3.11, Tkinter/ttk, pytest (unit + `gui`-marked tests), ruff, bandit.

**Spec:** `docs/superpowers/specs/2026-10-04-first-run-setup-design.md`

## Global Constraints

- Python commands run through `.venv\Scripts\python` (PowerShell 5.1: no `&&`; use `; if ($?) { ... }`).
- Commit messages are single-line. No `Co-Authored-By` trailer and no AI attribution of any kind.
- No new runtime dependencies. No subprocess calls are added. If one ever is, it must use `CREATE_NO_WINDOW`.
- Never write or delete the keyring entry ("CampaignScribe", "huggingface_token").
- The word "MeetingScribe" must not appear anywhere.
- Do not commit `CampaignScribe.spec` changes. If `git status` shows it modified, run `git checkout -- CampaignScribe.spec`.
- Full gate before each task's commit: `.venv\Scripts\python -m pytest -q`, `.venv\Scripts\python -m ruff check .`, `.venv\Scripts\python -m ruff format .`, `.venv\Scripts\python -m bandit -q -r app -ll`.
- CI installs only `requirements-dev.txt` (no torch, whisperx, pyannote, or fetched weights). New tests must not import those packages or rely on `models/`.
- A test must never open a real modal that waits (`wait_window`, `messagebox.*`, `simpledialog.*`). Patch it. A blocking modal hangs the Windows CI job until it times out.
- Exact user-facing strings (copy verbatim):
  - Welcome title: `Welcome to CampaignScribe`
  - Welcome body: `CampaignScribe transcribes your sessions on this PC. To name speakers and write summaries it needs an AI model — pick one to set up now. You can change it any time in Settings (⚙).`
  - Buttons: `Use a cloud AI` / `Use a free local model` / `Later`
  - Captions: `Claude, Google Gemini or OpenRouter — needs an API key` / `Ollama or LM Studio, runs on your PC`
  - First-campaign prompt: title `Create your first campaign?`, body `A campaign holds your speaker profiles and session history. You can also create one later from Home.`
  - Home empty state: title `No campaigns yet`, summary `Create a campaign to hold your speaker profiles and sessions, or import an existing speakers .json.`, button `＋ Create your first campaign`
  - Banner button: `Open Settings`
- Config flag name: `setup_welcome_shown`. Provider ids: cloud → `anthropic`, local → `ollama`.

## Review Focus

1. **A startup timer firing during tests.** `AppWindow` schedules `_run_startup_prompts` 300 ms after construction. Any GUI or smoke test that pumps events on a fresh config would open the welcome and hang CI. Expected: an autouse fixture in `tests/gui/conftest.py` and a new `tests/smoke/conftest.py` makes the welcome non-blocking. Task 4 pins this.
2. **The user closes the main window while the welcome is open.** Expected: no Settings dialog, no first-campaign prompt, and no exception. Task 4 pins this.
3. **The library-import prompt raises.** Expected: the error is logged and the welcome still runs. Task 4 pins this.
4. **Cancel in Settings after a preselection.** Expected: `llm_provider` in config is unchanged. Task 2 pins this.
5. **A search filter hides every campaign.** Expected: Home shows the normal "Select a campaign", not the empty state, because campaigns exist. Task 3 pins this.

---

### Task 1: First-run decision module

**Files:**
- Create: `app/core/first_run.py`
- Modify: `app/config.py` (`DEFAULT_CONFIG`, after the `"support_nudge_shown"` line)
- Test: `tests/unit/test_first_run.py`

**Interfaces:**
- Consumes: `app.config.load_config() -> dict`, `app.config.save_config(dict)`, `app.config.save_provider_key(provider_id, key)`, `app.core.llm.provider_ready(cfg) -> bool`.
- Produces: `first_run.SETUP_OFFERED_KEY = "setup_welcome_shown"`, `first_run.should_offer_setup(cfg: dict) -> bool`, `first_run.mark_setup_offered() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
"""first_run: offer the welcome once, only while no AI provider is ready."""

from __future__ import annotations

from app import config
from app.core import first_run


def test_offer_when_flag_unset_and_provider_not_ready():
    cfg = config.load_config()
    assert cfg["setup_welcome_shown"] is False
    assert first_run.should_offer_setup(cfg) is True


def test_no_offer_once_flag_set():
    cfg = config.load_config()
    cfg[first_run.SETUP_OFFERED_KEY] = True
    assert first_run.should_offer_setup(cfg) is False


def test_no_offer_when_cloud_key_stored():
    config.save_provider_key("anthropic", "sk-test")
    assert first_run.should_offer_setup(config.load_config()) is False


def test_no_offer_when_local_model_picked():
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    assert first_run.should_offer_setup(cfg) is False


def test_mark_setup_offered_persists_and_keeps_other_keys():
    cfg = config.load_config()
    cfg["theme_mode"] = "light"
    config.save_config(cfg)
    first_run.mark_setup_offered()
    after = config.load_config()
    assert after["setup_welcome_shown"] is True
    assert after["theme_mode"] == "light"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_first_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.first_run'`.

- [ ] **Step 3: Add the config default**

In `app/config.py`, `DEFAULT_CONFIG`, directly after `"support_nudge_shown": False,  ...`:

```python
    "setup_welcome_shown": False,  # first-launch welcome (pick an AI provider) has been offered
```

- [ ] **Step 4: Write the module**

`app/core/first_run.py`:

```python
"""First-launch setup offer (Tk-free).

The welcome is offered once per install, and only while the active AI provider
is not ready. The flag is set when the welcome is shown, whatever the user picks.
"""

from __future__ import annotations

from typing import Any

from app import config
from app.core import llm

SETUP_OFFERED_KEY = "setup_welcome_shown"


def should_offer_setup(cfg: dict[str, Any]) -> bool:
    """True when the welcome has never been shown and the active provider is not ready."""
    return not cfg.get(SETUP_OFFERED_KEY, False) and not llm.provider_ready(cfg)


def mark_setup_offered() -> None:
    """Persist the flag. Reload first so a concurrent write is not clobbered."""
    cfg = config.load_config()
    cfg[SETUP_OFFERED_KEY] = True
    config.save_config(cfg)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_first_run.py -v`
Expected: 5 passed.

- [ ] **Step 6: Full gate, then commit**

Run the full gate from Global Constraints. Then:

```
git add app/core/first_run.py app/config.py tests/unit/test_first_run.py
git commit -m "feat: first-run setup decision (one-time flag, provider readiness)"
```

---

### Task 2: Settings preselection and clickable banner

**Files:**
- Modify: `app/ui/settings_dialog.py` (`SettingsDialog.__init__` signature; `_build_llm_section`, directly after the block that sets `self._llm_current` from `cfg["llm_provider"]`)
- Modify: `app/ui/app_window.py` (`open_settings`; banner construction around `self.banner_text`)
- Test: `tests/gui/test_settings_initial_provider.py`, `tests/gui/test_banner_settings_button.py`

**Interfaces:**
- Consumes: `llm.PRESETS` (ids `anthropic`, `gemini`, `openrouter`, `ollama`, `lmstudio`, `custom`), `SettingsDialog.llm_provider_var`, `SettingsDialog._llm_current`.
- Produces: `SettingsDialog(master, initial_provider: str | None = None)`, `AppWindow.open_settings(initial_provider: str | None = None)`, and `AppWindow.banner_settings_btn` (a `ttk.Button`).

- [ ] **Step 1: Write the failing Settings tests**

`tests/gui/test_settings_initial_provider.py`:

```python
"""SettingsDialog(initial_provider=...) starts on that provider without saving it."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
from app.core import llm

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


def _open(root, **kw):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root, **kw)
    dlg.update_idletasks()
    return dlg


def test_opens_on_requested_provider(root):
    dlg = _open(root, initial_provider="gemini")
    try:
        assert dlg._llm_current == "gemini"
        assert dlg.llm_provider_var.get() == llm.PRESETS["gemini"].display_name
    finally:
        dlg.destroy()


def test_local_preselection_runs_detect_without_network(root, monkeypatch):
    from app.core.llm import local_detect

    calls = []

    def fake_detect(runtime, *a, **k):
        calls.append(runtime)
        return local_detect.DetectResult(runtime, False, [], "stub")

    monkeypatch.setattr(local_detect, "detect", fake_detect)
    dlg = _open(root, initial_provider="ollama")
    try:
        assert dlg._llm_current == "ollama"
    finally:
        dlg.destroy()


def test_cancel_leaves_configured_provider_unchanged(root):
    dlg = _open(root, initial_provider="gemini")
    dlg.destroy()  # Cancel = destroy without _save
    assert config.load_config()["llm_provider"] == "anthropic"


def test_unknown_provider_falls_back_to_configured(root):
    cfg = config.load_config()
    cfg["llm_provider"] = "openrouter"
    config.save_config(cfg)
    dlg = _open(root, initial_provider="nope")
    try:
        assert dlg._llm_current == "openrouter"
    finally:
        dlg.destroy()


def test_no_initial_provider_keeps_configured(root):
    dlg = _open(root)
    try:
        assert dlg._llm_current == "anthropic"
    finally:
        dlg.destroy()
```

Check `local_detect.detect`'s real signature and `DetectResult`'s field order in `app/core/llm/local_detect.py` before running. Adjust the fake to match exactly. Detect runs on a worker thread and is polled with `after(100, ...)`. `tests/gui/test_settings_llm.py` already handles this for local providers with `dlg._run_detect(_sync=True)`. Follow that pattern, or drain the poll before `destroy()`, so no callback fires on a destroyed dialog in a later test.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_initial_provider.py -v`
Expected: FAIL with `TypeError: SettingsDialog.__init__() got an unexpected keyword argument 'initial_provider'`.

- [ ] **Step 3: Implement the preselection**

In `app/ui/settings_dialog.py`:

```python
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, initial_provider: str | None = None):
        super().__init__(master)
        self._initial_provider = initial_provider
        # ... existing body unchanged ...
```

In `_build_llm_section`, directly after these existing lines:

```python
        self._llm_current = cfg.get("llm_provider", "anthropic")
        if self._llm_current not in llm.PRESETS:
            self._llm_current = "anthropic"
```

add:

```python
        # First-run welcome can open Settings on a chosen provider. Nothing is
        # persisted until Save, so Cancel keeps the configured provider.
        if self._initial_provider in llm.PRESETS:
            self._llm_current = self._initial_provider
```

Nothing else changes. The combobox's initial value is already built from `self._llm_current`, and `_load_llm_fields` auto-runs Detect for local runtimes.

- [ ] **Step 4: Run the Settings tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_initial_provider.py -v`
Expected: 5 passed.

- [ ] **Step 5: Write the failing AppWindow tests**

`tests/gui/test_banner_settings_button.py`:

```python
"""The setup banner has an Open Settings button; open_settings passes initial_provider."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stub",
            "smi_gpu_name": None,
        },
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


def test_banner_button_opens_settings(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "open_settings", lambda *a, **k: calls.append((a, k)))
    assert app.banner_settings_btn.cget("text") == "Open Settings"
    app.banner_settings_btn.invoke()
    assert calls == [((), {})]


def test_open_settings_passes_initial_provider(app, monkeypatch):
    seen = []

    class _FakeSettings(tk.Toplevel):
        def __init__(self, master, initial_provider=None):
            super().__init__(master)
            seen.append(initial_provider)
            self.after(0, self.destroy)

    monkeypatch.setattr("app.ui.app_window.SettingsDialog", _FakeSettings)
    app.open_settings(initial_provider="ollama")
    app.open_settings()
    assert seen == ["ollama", None]
```

The banner button's `command` must look up `self.open_settings` at click time, so the instance patch takes effect. Use `command=lambda: self.open_settings()`, not `command=self.open_settings`.

- [ ] **Step 6: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_banner_settings_button.py -v`
Expected: FAIL with `AttributeError: ... 'banner_settings_btn'`.

- [ ] **Step 7: Implement the banner button and the pass-through**

In `app/ui/app_window.py`, directly after `self.banner_text.pack(side="left")`:

```python
        self.banner_settings_btn = ttk.Button(
            banner_inner,
            text="Open Settings",
            style=BTN_GHOST,
            command=lambda: self.open_settings(),
        )
        self.banner_settings_btn.pack(side="right")
```

Change `open_settings`:

```python
    def open_settings(self, initial_provider: str | None = None):
        old_mode = config.load_config().get("theme_mode", "dark")
        dlg = SettingsDialog(self, initial_provider=initial_provider)
        self.wait_window(dlg)
        # ... rest unchanged ...
```

Existing callers such as the topbar ⚙ button keep calling `open_settings()` with no arguments.

- [ ] **Step 8: Run both test files, full gate, commit**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_initial_provider.py tests/gui/test_banner_settings_button.py -v`
Expected: 7 passed. Then run the full gate.

```
git add app/ui/settings_dialog.py app/ui/app_window.py tests/gui/test_settings_initial_provider.py tests/gui/test_banner_settings_button.py
git commit -m "feat: Settings can open on a chosen provider; Open Settings button on the setup banner"
```

---

### Task 3: Home empty state and public new_campaign

**Files:**
- Modify: `app/ui/home_tab.py` (`__init__` detail pane after `self.new_session_btn`; `_clear_detail`; `select_campaign`; `select_uncategorized`; rename `_new_campaign` to `new_campaign` and update the "＋ New campaign…" button's `command`)
- Test: `tests/gui/test_home_empty_state.py`

**Interfaces:**
- Consumes: `library.list_campaigns()`, `library.create_campaign(name) -> slug`, `db.list_sessions(campaign_slug=db.UNCATEGORIZED)`, `db.create_session(display_name, campaign_name="", campaign_slug=None)`. Check the real signature in `app/data/db.py`; a session with no slug is uncategorized.
- Produces: `HomeTab.new_campaign() -> None` (public; Task 4 calls it), `HomeTab.first_campaign_btn`, and module constants `EMPTY_TITLE` and `EMPTY_SUMMARY`.

- [ ] **Step 1: Write the failing tests**

`tests/gui/test_home_empty_state.py`:

```python
"""Home shows an actionable empty state only when there is nothing at all."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.core import library
from app.data import db

pytestmark = pytest.mark.gui


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stub",
            "smi_gpu_name": None,
        },
    )
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


def _shown(widget) -> bool:
    return widget.winfo_manager() == "grid"


def test_empty_library_shows_empty_state(app):
    home = app.home_tab
    from app.ui import home_tab

    assert home.title_var.get() == home_tab.EMPTY_TITLE == "No campaigns yet"
    assert home.summary_var.get() == home_tab.EMPTY_SUMMARY
    assert _shown(home.first_campaign_btn)
    assert not _shown(home.new_session_btn)


def test_create_button_creates_and_hides_empty_state(app, monkeypatch):
    home = app.home_tab
    monkeypatch.setattr("app.ui.home_tab.simpledialog.askstring", lambda *a, **k: "Strahd")
    home.first_campaign_btn.invoke()
    assert [r["display_name"] for r in library.list_campaigns()] == ["Strahd"]
    assert home.title_var.get() == "Strahd"
    assert not _shown(home.first_campaign_btn)
    assert _shown(home.new_session_btn)


def test_cancelled_name_keeps_empty_state(app, monkeypatch):
    home = app.home_tab
    monkeypatch.setattr("app.ui.home_tab.simpledialog.askstring", lambda *a, **k: None)
    home.new_campaign()
    assert home.title_var.get() == "No campaigns yet"


def test_existing_campaign_hidden_by_search_is_not_empty_state(app):
    library.create_campaign("Strahd")
    home = app.home_tab
    home.search_var.set("zzz")  # trace calls _refresh_campaigns
    assert home.title_var.get() == "Select a campaign"
    assert not _shown(home.first_campaign_btn)


def test_loose_sessions_mean_not_empty(app):
    db.create_session("Loose")
    home = app.home_tab
    home.on_show()
    assert home.title_var.get() != "No campaigns yet"
    assert not _shown(home.first_campaign_btn)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_home_empty_state.py -v`
Expected: FAIL with `ImportError` or `AttributeError` on `EMPTY_TITLE` or `first_campaign_btn`.

- [ ] **Step 3: Implement**

Module level in `app/ui/home_tab.py`, next to `UNCATEGORIZED_LABEL`:

```python
EMPTY_TITLE = "No campaigns yet"
EMPTY_SUMMARY = (
    "Create a campaign to hold your speaker profiles and sessions, "
    "or import an existing speakers .json."
)
```

In `__init__`, directly after the three `self.new_session_btn` lines (create, grid, disable):

```python
        self.first_campaign_btn = ttk.Button(
            right, text="＋ Create your first campaign", style=BTN_ACCENT, command=self.new_campaign
        )
        self.first_campaign_btn.grid(row=2, column=0, sticky="w", pady=(0, S_2))
        self.first_campaign_btn.grid_remove()
```

Rename `def _new_campaign(self):` to `def new_campaign(self):`. Change the "＋ New campaign…" button to `command=self.new_campaign`. Grep `tests/` and `app/` for `_new_campaign` and update every remaining reference.

Add helpers next to `_clear_detail`:

```python
    def _library_is_empty(self) -> bool:
        return not library.list_campaigns() and not db.list_sessions(
            campaign_slug=db.UNCATEGORIZED
        )

    def _set_empty_state(self, empty: bool) -> None:
        if empty:
            self.title_var.set(EMPTY_TITLE)
            self.summary_var.set(EMPTY_SUMMARY)
            self.new_session_btn.grid_remove()
            self.first_campaign_btn.grid()
        else:
            self.first_campaign_btn.grid_remove()
            self.new_session_btn.grid()
```

At the end of `_clear_detail`, add `self._set_empty_state(self._library_is_empty())`. At the start of `select_campaign` and `select_uncategorized`, add `self._set_empty_state(False)`.

`_refresh_campaigns` always lists the Uncategorized bucket, but it calls `_clear_detail` when nothing is selected, so an empty library lands in the empty state.

- [ ] **Step 4: Run the tests, then the existing Home and campaign suites**

Run: `.venv\Scripts\python -m pytest tests/gui/test_home_empty_state.py tests/gui/test_home_tab.py tests/smoke -v`
Expected: all pass. If an existing test asserted "Select a campaign" on an empty library, update that assertion to the empty-state title and note it in your report.

- [ ] **Step 5: Full gate, commit**

```
git add app/ui/home_tab.py tests/gui/test_home_empty_state.py
git commit -m "feat: Home empty state with Create your first campaign; public HomeTab.new_campaign"
```

If other test files changed because of the rename, add them too.

---

### Task 4: Welcome dialog and startup flow

**Files:**
- Create: `app/ui/welcome_dialog.py`
- Modify: `app/ui/app_window.py` (imports; the `self.after(300, ...)` startup line; new methods `_run_startup_prompts`, `_maybe_first_run_setup`, `_maybe_offer_first_campaign`)
- Modify: `tests/gui/conftest.py` (add the autouse welcome guard)
- Create: `tests/smoke/conftest.py`
- Test: `tests/gui/test_welcome_dialog.py`, `tests/gui/test_welcome_flow.py`

**Interfaces:**
- Consumes: `first_run.should_offer_setup`, `first_run.mark_setup_offered` (Task 1); `AppWindow.open_settings(initial_provider=...)` (Task 2); `HomeTab.new_campaign()` (Task 3); `AppWindow.open_home()`; `library.list_campaigns()`; `config.log_exception(context: str, exc: BaseException)`.
- Produces: `welcome_dialog.WelcomeDialog(master)` with `.choice`, `.cloud_btn`, `.local_btn`, `.later_btn`; `welcome_dialog.ask_setup_choice(master) -> str | None` returning `"cloud"`, `"local"` or `None`; `AppWindow._run_startup_prompts()`.

- [ ] **Step 1: Add the CI guards first**

Append to `tests/gui/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _welcome_never_blocks(monkeypatch):
    """AppWindow schedules startup prompts on a timer. On a fresh config the
    welcome would open a modal that waits, which hangs CI if a test pumps events.
    Flow tests override this with their own recorder."""
    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", lambda master: None)
```

Create `tests/smoke/conftest.py`:

```python
"""Smoke-test fixtures: startup prompts must never open a blocking modal."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _welcome_never_blocks(monkeypatch):
    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", lambda master: None)
```

These patch a module created in Step 4. Run Steps 2 to 4 before running any suite that uses these conftests.

- [ ] **Step 2: Write the failing dialog tests**

`tests/gui/test_welcome_dialog.py`:

```python
"""WelcomeDialog records the user's choice and closes."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


def _dlg(root):
    from app.ui.welcome_dialog import WelcomeDialog

    d = WelcomeDialog(root)
    d.update_idletasks()
    return d


@pytest.mark.parametrize(
    "button, expected", [("cloud_btn", "cloud"), ("local_btn", "local"), ("later_btn", None)]
)
def test_buttons_set_choice_and_close(root, button, expected):
    d = _dlg(root)
    getattr(d, button).invoke()
    assert d.choice == expected
    assert not d.winfo_exists()


def test_copy_matches_spec(root):
    from app.ui import welcome_dialog as w

    d = _dlg(root)
    try:
        assert d.title() == "Welcome to CampaignScribe"
        assert d.cloud_btn.cget("text") == "Use a cloud AI"
        assert d.local_btn.cget("text") == "Use a free local model"
        assert d.later_btn.cget("text") == "Later"
        assert w.CLOUD_CAPTION == "Claude, Google Gemini or OpenRouter — needs an API key"
        assert w.LOCAL_CAPTION == "Ollama or LM Studio, runs on your PC"
        assert w.BODY.startswith("CampaignScribe transcribes your sessions on this PC.")
    finally:
        d.destroy()


def test_escape_and_close_box_mean_later(root):
    d = _dlg(root)
    assert d.bind("<Escape>")  # binding exists
    d._choose(None)  # what both Escape and WM_DELETE_WINDOW call
    assert d.choice is None
    assert not d.winfo_exists()
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_welcome_dialog.py -v -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.welcome_dialog'`. The conftest guard also fails to import the module. That's expected until Step 4.

- [ ] **Step 4: Write the dialog**

`app/ui/welcome_dialog.py`:

```python
"""First-launch welcome: choose a cloud or local AI provider, or skip for now."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, LBL_TITLE

TITLE = "Welcome to CampaignScribe"
BODY = (
    "CampaignScribe transcribes your sessions on this PC. To name speakers and write "
    "summaries it needs an AI model — pick one to set up now. You can change it any "
    "time in Settings (⚙)."
)
CLOUD_CAPTION = "Claude, Google Gemini or OpenRouter — needs an API key"
LOCAL_CAPTION = "Ollama or LM Studio, runs on your PC"


class WelcomeDialog(tk.Toplevel):
    """Modal welcome. ``choice`` is "cloud", "local" or None once it closes."""

    def __init__(self, master):
        super().__init__(master)
        self.choice: str | None = None
        self.title(TITLE)
        self.transient(master)
        self.resizable(False, False)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=TITLE, style=LBL_TITLE).pack(anchor="w")
        ttk.Label(body, text=BODY, wraplength=440, justify="left").pack(
            anchor="w", pady=(8, 16)
        )

        self.cloud_btn = ttk.Button(
            body, text="Use a cloud AI", style=BTN_ACCENT, command=lambda: self._choose("cloud")
        )
        self.cloud_btn.pack(fill="x")
        ttk.Label(body, text=CLOUD_CAPTION, style=LBL_DIM).pack(anchor="w", pady=(2, 12))

        self.local_btn = ttk.Button(
            body,
            text="Use a free local model",
            style=BTN_ACCENT,
            command=lambda: self._choose("local"),
        )
        self.local_btn.pack(fill="x")
        ttk.Label(body, text=LOCAL_CAPTION, style=LBL_DIM).pack(anchor="w", pady=(2, 16))

        self.later_btn = ttk.Button(
            body, text="Later", style=BTN_GHOST, command=lambda: self._choose(None)
        )
        self.later_btn.pack(anchor="e")

        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(None))
        self.bind("<Escape>", lambda _e: self._choose(None))
        self.grab_set()
        self.cloud_btn.focus_set()

    def _choose(self, choice: str | None) -> None:
        self.choice = choice
        self.destroy()


def ask_setup_choice(master) -> str | None:
    """Show the welcome modally and return "cloud", "local" or None."""
    dlg = WelcomeDialog(master)
    master.wait_window(dlg)
    return dlg.choice
```

- [ ] **Step 5: Run the dialog tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_welcome_dialog.py -v`
Expected: 5 passed.

- [ ] **Step 6: Write the failing flow tests**

`tests/gui/test_welcome_flow.py`:

```python
"""Startup prompts: library import, then the one-time welcome, then the first-campaign offer."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
from app.core import library
from app.data import db

pytestmark = pytest.mark.gui


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stub",
            "smi_gpu_name": None,
        },
    )
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
        try:
            win.destroy()
        except tk.TclError:
            pass  # a test may already have closed the main window


@pytest.fixture
def rec(monkeypatch, app):
    """Record welcome shows, Settings opens, yes/no prompts and new_campaign calls."""
    r = {"welcome": 0, "choice": None, "settings": [], "asked": [], "answer": True, "new": 0}

    def fake_choice(master):
        r["welcome"] += 1
        return r["choice"]

    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", fake_choice)
    monkeypatch.setattr(app, "open_settings", lambda initial_provider=None: r["settings"].append(initial_provider))

    def fake_ask(title, msg, **k):
        r["asked"].append(title)
        return r["answer"]

    monkeypatch.setattr("app.ui.app_window.messagebox.askyesno", fake_ask)

    def fake_new():
        r["new"] += 1

    monkeypatch.setattr(app.home_tab, "new_campaign", fake_new)
    return r


def test_fresh_config_shows_welcome_once(app, rec):
    app._run_startup_prompts()
    app._run_startup_prompts()  # e.g. the theme-change rebuild
    assert rec["welcome"] == 1
    assert config.load_config()["setup_welcome_shown"] is True


@pytest.mark.parametrize("choice, provider", [("cloud", "anthropic"), ("local", "ollama")])
def test_choice_opens_settings_then_offers_first_campaign(app, rec, choice, provider):
    rec["choice"] = choice
    app._run_startup_prompts()
    assert rec["settings"] == [provider]
    assert rec["asked"] == ["Create your first campaign?"]
    assert rec["new"] == 1
    assert app.notebook.select() == str(app.home_tab)


def test_declining_first_campaign_creates_nothing(app, rec):
    rec["choice"] = "cloud"
    rec["answer"] = False
    app._run_startup_prompts()
    assert rec["new"] == 0


def test_later_opens_nothing(app, rec):
    rec["choice"] = None
    app._run_startup_prompts()
    assert rec["welcome"] == 1
    assert rec["settings"] == []
    assert rec["asked"] == []


def test_existing_campaign_skips_offer(app, rec):
    library.create_campaign("Strahd")
    rec["choice"] = "cloud"
    app._run_startup_prompts()
    assert rec["settings"] == ["anthropic"]
    assert rec["asked"] == []


def test_ready_provider_shows_no_welcome(app, rec):
    config.save_provider_key("anthropic", "sk-test")
    app._run_startup_prompts()
    assert rec["welcome"] == 0


def test_library_import_failure_still_offers_welcome(app, rec, monkeypatch):
    def boom():
        raise RuntimeError("import exploded")

    monkeypatch.setattr(app, "_maybe_offer_library_import", boom)
    app._run_startup_prompts()
    assert rec["welcome"] == 1


def test_main_window_closed_during_welcome_does_nothing_more(app, rec, monkeypatch):
    def close_then_choose(master):
        rec["welcome"] += 1
        master.destroy()
        return "cloud"

    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", close_then_choose)
    app._run_startup_prompts()  # must not raise
    assert rec["settings"] == []
    assert rec["asked"] == []


def test_startup_timer_targets_run_startup_prompts(app):
    assert app._migration_after_id is not None
    info = app.tk.call("after", "info", app._migration_after_id)
    assert "_run_startup_prompts" in str(info)
```

The last test reads the pending `after` script. Tkinter registers the callback under a name that contains the bound method's name. If that check proves brittle on your Tk build, replace it with a check that `_maybe_offer_library_import` is no longer scheduled directly. Report the change.

- [ ] **Step 7: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_welcome_flow.py -v`
Expected: FAIL with `AttributeError: ... '_run_startup_prompts'`.

- [ ] **Step 8: Implement the startup flow in `app/ui/app_window.py`**

Imports: change `from app.core import library, llm, notices, privacy` to `from app.core import first_run, library, llm, notices, privacy`. Import `welcome_dialog` as a module, `from app.ui import welcome_dialog`, so test patches on `app.ui.welcome_dialog.ask_setup_choice` take effect.

Replace the startup line:

```python
        # Startup prompts (library migration, then first-run welcome) after the window shows.
        self._migration_after_id = self.after(300, self._run_startup_prompts)
```

Add these methods after `_maybe_offer_library_import`, which stays unchanged because smoke tests call it directly:

```python
    def _run_startup_prompts(self):
        """One prompt at a time: library import first, then the first-run welcome.
        A failure in one step is logged and never blocks the next."""
        for step in (self._maybe_offer_library_import, self._maybe_first_run_setup):
            if not self.winfo_exists():
                return
            try:
                step()
            except Exception as e:  # noqa: BLE001
                config.log_exception(f"startup prompt {getattr(step, '__name__', step)}", e)

    def _maybe_first_run_setup(self):
        if not first_run.should_offer_setup(config.load_config()):
            return
        # Mark before showing, so a crash in the dialog cannot repeat it every launch.
        first_run.mark_setup_offered()
        choice = welcome_dialog.ask_setup_choice(self)
        if not self.winfo_exists():
            return  # main window closed while the welcome was open
        provider = {"cloud": "anthropic", "local": "ollama"}.get(choice or "")
        if provider is None:
            return
        self.open_settings(initial_provider=provider)
        if self.winfo_exists():
            self._maybe_offer_first_campaign()

    def _maybe_offer_first_campaign(self):
        if library.list_campaigns():
            return
        if messagebox.askyesno(
            "Create your first campaign?",
            "A campaign holds your speaker profiles and session history. "
            "You can also create one later from Home.",
            parent=self,
        ):
            self.open_home()
            self.home_tab.new_campaign()
```

`winfo_exists()` on a destroyed Tk root may raise `TclError` instead of returning 0. If `test_main_window_closed_during_welcome_does_nothing_more` errors that way, wrap the check in a small helper:

```python
    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False
```

Then use `self._alive()` in all three places.

- [ ] **Step 9: Run the flow tests, the dialog tests and the startup-related smoke tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_welcome_flow.py tests/gui/test_welcome_dialog.py tests/smoke -v`
Expected: all pass.

- [ ] **Step 10: CI-condition check, full gate, commit**

Run the whole suite as CI sees it: fetched weights moved aside and ML packages hidden. Restore the folder afterwards, even on failure.

```powershell
Rename-Item models models.ci-hidden
try { .venv\Scripts\python -c "import sys, pytest; [sys.modules.__setitem__(m, None) for m in ('whisperx','pyannote','torch','torchaudio','huggingface_hub')]; sys.exit(pytest.main(['-q','-p','no:cacheprovider','tests']))" } finally { Rename-Item models.ci-hidden models }
```

Expected: all pass, with 1 skip for the pyannote metrics test, and no hang. Then run the full gate.

```
git add app/ui/welcome_dialog.py app/ui/app_window.py tests/gui/conftest.py tests/smoke/conftest.py tests/gui/test_welcome_dialog.py tests/gui/test_welcome_flow.py
git commit -m "feat: first-launch welcome hands off to Settings and offers a first campaign"
```

---

## Manual check (controller, after Task 4)

Run the app from source on a fresh profile. Point `%APPDATA%` at an empty temp folder for the process only. Then confirm:

1. The welcome appears once.
2. **Use a free local model** opens Settings on Ollama, with the Detect message visible.
3. Cancel leaves the banner, which has an **Open Settings** button.
4. The first-campaign prompt appears, and Yes leads to the New campaign prompt.
5. Relaunching with the same profile shows no welcome.
