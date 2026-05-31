# Theme Switch (Dark / Light / System) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick Dark, Light, or System (follow-the-OS) from Settings; the choice persists and is applied by rebuilding the window, with a guard that blocks switching while a job is running.

**Architecture:** `theme.py` already has both palettes + `set_theme_variant()`. We add a pure `resolve_variant(mode)` (mode → `"dark"|"light"`, detecting the OS theme for `"system"` via `darkdetect`→registry→dark fallback), have `apply_theme()` read the persisted `theme_mode` from config and resolve it before configuring styles, add a Settings dropdown, and apply changes by **destroying + reconstructing** `AppWindow` inside a small relaunch loop in `main.py`. A busy-guard (each tab exposes `self._busy`) blocks rebuilds mid-job.

**Tech Stack:** Python 3.11, Tkinter/ttk, the existing `app.ui.theme` engine, `darkdetect` (tiny pure-python OS-theme detector), `winreg` (stdlib fallback).

**Repo:** `Imagination-Industries-LLC/CampaignScribe`. Phase 1, unit 2 of 3 (Privacy ✅ → **Theme** → Feedback/Support Hub). Branch off `main`: `feature/theme-switch`.

---

## Scope & ground rules
- One of three independent Phase 1 plans; produces working, testable software on its own.
- **Project rules:** plain commits (NO AI attribution); no predecessor-product name references; `CREATE_NO_WINDOW` on any subprocess (none added); ruff-clean; tests green; GPU-preferred unaffected.
- **Out of scope (deferred):** the optional `system`-mode live listener that auto-rebuilds when the OS theme changes mid-session (spec "phase 2"). We resolve `system` on launch/rebuild only.

## Existing-code facts (verified)
- `app/ui/theme.py`: `ThemeVariant = Literal["dark","light"]`; module global `_active_variant` (default `"dark"`); `set_theme_variant(variant)` validates + sets it; `color(name)` reads `_PALETTES[_active_variant][name]`; `apply_theme(root)` calls `_register_bundled_fonts/_configure_root_window/_configure_styles/_configure_tk_widget_defaults/_set_window_icon`. Palette BG: dark `#0D1018`, light `#ECE6D3`.
- `app/config.py`: `DEFAULT_CONFIG` dict; `save_config` **only persists keys present in `DEFAULT_CONFIG`** (allowlist), so a new key MUST be added there to persist.
- `app/ui/app_window.py`: `apply_theme(self)` is the first call in `__init__`; `open_settings()` opens `SettingsDialog` then fans `on_settings_changed` to tabs; `_on_close()` saves window geometry to config then `destroy()`.
- `app/ui/settings_dialog.py`: grid-based dialog; rows 0-4 (api/hf/out/model/speakers), then a button frame; `_save()` writes config.
- Worker tabs (`discover_tab`, `transcribe_tab`, `refine_tab`, `summarize_tab`) each set `self._busy` True/False around their worker thread. `build_profile_tab`/`history_tab` have no `_busy` (treated as not-busy via `getattr(..., False)`).
- `main.py` `main()`: constructs `AppWindow()` once, `win.mainloop()`, returns 0.

## File Structure
- **Modify `app/config.py`** — add `theme_mode: "dark"` to `DEFAULT_CONFIG`.
- **Modify `app/ui/theme.py`** — add `resolve_variant(mode)` + `_detect_system_variant()`; `apply_theme` resolves `theme_mode` from config before configuring.
- **Modify `requirements.txt`** + **`CampaignScribe.spec`** — add `darkdetect` (dep + hiddenimport).
- **Modify `app/ui/app_window.py`** — `_rebuild_requested` flag, `_save_window_geometry()` (refactor from `_on_close`), `_any_tab_busy()`, `request_rebuild()`, `_handle_theme_change()`, theme-change detection in `open_settings()`.
- **Modify `app/ui/settings_dialog.py`** — Theme dropdown (Dark/Light/System) persisted as `theme_mode`.
- **Modify `main.py`** — relaunch loop honoring `request_rebuild()`.
- **Create tests** — `tests/unit/test_theme_resolve.py`, `tests/unit/test_config_theme.py`, `tests/smoke/test_theme_switch.py`.

---

### Task 1: Config — persist `theme_mode`

**Files:**
- Modify: `app/config.py` (`DEFAULT_CONFIG`)
- Test: `tests/unit/test_config_theme.py`

- [ ] **Step 1: Write the failing test**

```python
"""theme_mode persists through config save/load and survives the key allowlist."""
from __future__ import annotations

from app import config


def test_theme_mode_default_is_dark():
    assert config.DEFAULT_CONFIG["theme_mode"] == "dark"


def test_theme_mode_persists_through_allowlist():
    config.save_config({"theme_mode": "light"})
    assert config.load_config()["theme_mode"] == "light"


def test_theme_mode_falls_back_to_default_when_absent():
    # A config file missing theme_mode loads the default.
    import json

    config.get_config_path().write_text(json.dumps({"default_num_speakers": 4}), encoding="utf-8")
    assert config.load_config()["theme_mode"] == "dark"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_config_theme.py -v`
Expected: FAIL (`KeyError: 'theme_mode'`).

- [ ] **Step 3: Add the key**

In `app/config.py`, add `"theme_mode": "dark",` to the `DEFAULT_CONFIG` dict (e.g. immediately after `"default_num_speakers": 5,`):
```python
    "default_num_speakers": 5,
    "theme_mode": "dark",
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_config_theme.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/unit/test_config_theme.py
git commit -m "feat: persist theme_mode in config (default dark)"
```

---

### Task 2: theme.py — `resolve_variant` + config-aware `apply_theme`

**Files:**
- Modify: `app/ui/theme.py`
- Test: `tests/unit/test_theme_resolve.py`

- [ ] **Step 1: Write the failing tests**

```python
"""theme.resolve_variant routing + variant→color, and apply_theme honoring config."""
from __future__ import annotations

import pytest

from app.ui import theme


@pytest.fixture(autouse=True)
def restore_variant():
    prev = theme._active_variant
    yield
    theme.set_theme_variant(prev)


def test_resolve_variant_dark_and_light():
    assert theme.resolve_variant("dark") == "dark"
    assert theme.resolve_variant("light") == "light"


def test_resolve_variant_unknown_defaults_to_dark():
    assert theme.resolve_variant("banana") == "dark"


def test_resolve_variant_system_uses_detector(monkeypatch):
    monkeypatch.setattr(theme, "_detect_system_variant", lambda: "light")
    assert theme.resolve_variant("system") == "light"
    monkeypatch.setattr(theme, "_detect_system_variant", lambda: "dark")
    assert theme.resolve_variant("system") == "dark"


def test_detect_system_variant_returns_valid_variant():
    # On any platform/runner it must return one of the two valid variants
    # (never None, never "system").
    assert theme._detect_system_variant() in ("dark", "light")


def test_set_variant_switches_palette_colors():
    theme.set_theme_variant("light")
    assert theme.color("BG") == "#ECE6D3"
    theme.set_theme_variant("dark")
    assert theme.color("BG") == "#0D1018"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_theme_resolve.py -v`
Expected: FAIL (`AttributeError: module 'app.ui.theme' has no attribute 'resolve_variant'`).

- [ ] **Step 3: Implement in `app/ui/theme.py`**

Add these two functions immediately AFTER `set_theme_variant` (around line 61, before `color`):

```python
def _detect_system_variant() -> ThemeVariant:
    """Best-effort OS appearance detection: darkdetect → Windows registry →
    dark. Always returns a valid variant (never None)."""
    # 1. darkdetect (cross-platform, tiny). Lazily imported so a missing
    #    package never breaks non-system modes.
    try:
        import darkdetect

        result = darkdetect.theme()  # "Dark" | "Light" | None
        if result == "Light":
            return "light"
        if result == "Dark":
            return "dark"
    except Exception:
        pass
    # 2. Windows registry: AppsUseLightTheme (1 = light, 0 = dark).
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        pass
    # 3. Fallback: the app ships dark.
    return "dark"


def resolve_variant(mode: str) -> ThemeVariant:
    """Map a theme_mode ('dark' | 'light' | 'system') to a concrete variant.
    Unknown modes resolve to 'dark' (safe default)."""
    if mode == "light":
        return "light"
    if mode == "system":
        return _detect_system_variant()
    return "dark"
```

Then change `apply_theme` to resolve the persisted mode first. Replace the body so it begins by reading config:

```python
def apply_theme(root: tk.Tk) -> None:
    """Configure ttk styles, classic-Tk colors, fonts, and the window icon.

    Reads the persisted ``theme_mode`` from config, resolves it to a concrete
    palette variant, then configures everything. Call once at the top of
    ``AppWindow.__init__`` before any widget is constructed. To switch at
    runtime, persist a new ``theme_mode`` and rebuild the window.
    """
    from app import config

    set_theme_variant(resolve_variant(config.load_config().get("theme_mode", "dark")))
    _register_bundled_fonts(root)
    _configure_root_window(root)
    _configure_styles(root)
    _configure_tk_widget_defaults(root)
    _set_window_icon(root)
```

(`from app import config` lazily inside `apply_theme` avoids any import-order concern; `config` does not import `theme`, so there is no cycle.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_theme_resolve.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ui/theme.py tests/unit/test_theme_resolve.py
git commit -m "feat: add resolve_variant + OS detection; apply_theme honors theme_mode"
```

---

### Task 3: `darkdetect` dependency + PyInstaller hidden import

**Files:**
- Modify: `requirements.txt`
- Modify: `CampaignScribe.spec`

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add `darkdetect` on its own line among the light app deps (e.g. right after `python-docx`):
```
python-docx
darkdetect
```

- [ ] **Step 2: Add the hidden import**

`darkdetect` is imported lazily (inside `_detect_system_variant`), so PyInstaller's static analysis can miss it. In `CampaignScribe.spec`, add `'darkdetect'` to the `hiddenimports` list. The line currently is:
```python
hiddenimports = ['anthropic', 'keyring.backends.Windows', 'docx', 'ffmpeg', 'app', 'app.ui.app_window']
```
Change to:
```python
hiddenimports = ['anthropic', 'keyring.backends.Windows', 'docx', 'ffmpeg', 'app', 'app.ui.app_window', 'darkdetect']
```

- [ ] **Step 3: Install + verify**

Run: `.venv\Scripts\python -m pip install darkdetect`
Run: `.venv\Scripts\python -c "import darkdetect; print('darkdetect', darkdetect.theme())"` → prints `darkdetect <Dark|Light|None>`.
Run: `.venv\Scripts\python -c "compile(open('CampaignScribe.spec').read(),'x','exec'); print('spec ok')"` → `spec ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt CampaignScribe.spec
git commit -m "build: add darkdetect dependency + hidden import for System theme"
```

---

### Task 4: AppWindow — rebuild plumbing + busy guard

**Files:**
- Modify: `app/ui/app_window.py`
- Test: `tests/smoke/test_theme_switch.py` (created here; extended in Task 6)

- [ ] **Step 1: Write the failing smoke tests**

Create `tests/smoke/test_theme_switch.py`:
```python
"""Headless smoke: theme rebuild plumbing + busy guard."""
from __future__ import annotations

import tkinter as tk

import pytest

from app.ui import theme

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def restore_variant():
    prev = theme._active_variant
    yield
    theme.set_theme_variant(prev)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None,
                 "error": "stub", "smi_gpu_name": None},
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
        try:
            win.destroy()
        except tk.TclError:
            pass


def test_fresh_window_not_requesting_rebuild(app):
    assert app._rebuild_requested is False


def test_any_tab_busy_reflects_tab_state(app):
    assert app._any_tab_busy() is False
    app.discover_tab._busy = True
    assert app._any_tab_busy() is True
    app.discover_tab._busy = False


def test_request_rebuild_sets_flag(app):
    app.request_rebuild()
    assert app._rebuild_requested is True


def test_handle_theme_change_blocks_while_busy(app, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "app.ui.app_window.messagebox.showinfo",
        lambda *a, **k: shown.setdefault("msg", True),
    )
    app.transcribe_tab._busy = True
    app._handle_theme_change()
    assert app._rebuild_requested is False  # blocked
    assert shown.get("msg") is True
    app.transcribe_tab._busy = False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_theme_switch.py -v`
Expected: FAIL (`AttributeError: 'AppWindow' object has no attribute '_rebuild_requested'` / `_any_tab_busy` / `request_rebuild` / `_handle_theme_change`).

- [ ] **Step 3: Implement in `app/ui/app_window.py`**

(a) Add `from tkinter import messagebox` to the top imports if not present (the file uses `from tkinter import ttk`; add `messagebox`):
```python
from tkinter import messagebox, ttk
```

(b) Initialize the flag as the FIRST line of `AppWindow.__init__` (right after `super().__init__()`):
```python
        super().__init__()
        self._rebuild_requested = False
```

(c) Refactor geometry-saving out of `_on_close`. Replace the existing `_on_close` with:
```python
    def _save_window_geometry(self):
        try:
            cfg = config.load_config()
            cfg["window_width"] = self.winfo_width()
            cfg["window_height"] = self.winfo_height()
            cfg["window_x"] = self.winfo_x()
            cfg["window_y"] = self.winfo_y()
            config.save_config(cfg)
        except Exception:
            pass

    def _on_close(self):
        self._save_window_geometry()
        self.destroy()
```

(d) Add the rebuild + busy-guard methods (next to `open_settings`):
```python
    def _any_tab_busy(self) -> bool:
        return any(getattr(widget, "_busy", False) for widget, _label, _icon in self._tab_specs)

    def request_rebuild(self):
        """Persist geometry, flag a rebuild, and close the window so the
        entry-point relaunch loop constructs a fresh one (new theme applied)."""
        self._save_window_geometry()
        self._rebuild_requested = True
        self.destroy()

    def _handle_theme_change(self):
        """Apply a theme_mode change by rebuilding — unless a job is running,
        in which case defer to next launch (the new mode is already persisted)."""
        if self._any_tab_busy():
            messagebox.showinfo(
                "Theme",
                "A job is currently running. The new theme will be applied the "
                "next time you launch CampaignScribe.",
                parent=self,
            )
            return
        self.request_rebuild()
```

(e) Detect the change in `open_settings`. Replace `open_settings` with:
```python
    def open_settings(self):
        old_mode = config.load_config().get("theme_mode", "dark")
        dlg = SettingsDialog(self)
        self.wait_window(dlg)
        self._refresh_banner()
        for tab in (
            self.discover_tab,
            self.refine_tab,
            self.build_profile_tab,
            self.history_tab,
            self.transcribe_tab,
            self.summarize_tab,
        ):
            if hasattr(tab, "on_settings_changed"):
                tab.on_settings_changed()
        new_mode = config.load_config().get("theme_mode", "dark")
        if new_mode != old_mode:
            self._handle_theme_change()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_theme_switch.py -v`
Expected: PASS (4 tests on a display; SKIP headless).

- [ ] **Step 5: Commit**

```bash
git add app/ui/app_window.py tests/smoke/test_theme_switch.py
git commit -m "feat: AppWindow theme-rebuild plumbing + busy guard"
```

---

### Task 5: Settings — Theme dropdown

**Files:**
- Modify: `app/ui/settings_dialog.py`

- [ ] **Step 1: Add the Theme row**

In `SettingsDialog.__init__`, insert this block AFTER the "Default # speakers" Spinbox block (after its `row += 1`) and BEFORE `btn_frame = ttk.Frame(self)`:
```python
        ttk.Label(self, text="Theme:").grid(row=row, column=0, sticky="w", **pad)
        self.theme_var = tk.StringVar(value=cfg.get("theme_mode", "dark").capitalize())
        ttk.Combobox(
            self,
            textvariable=self.theme_var,
            state="readonly",
            width=20,
            values=["Dark", "Light", "System"],
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1
```

- [ ] **Step 2: Persist it in `_save`**

In `_save`, add the theme_mode line alongside the other `cfg[...]` assignments (before `config.save_config(cfg)`):
```python
            cfg["default_num_speakers"] = int(self.spk_var.get() or 5)
            cfg["theme_mode"] = self.theme_var.get().lower()
            config.save_config(cfg)
```

- [ ] **Step 3: Verify the dialog builds + persists**

Run:
```
.venv\Scripts\python -c "import os; os.environ.setdefault('APPDATA', os.path.expanduser('~')); import tkinter as tk; from app.ui.theme import apply_theme; r=tk.Tk(); apply_theme(r); r.withdraw(); from app.ui.settings_dialog import SettingsDialog; d=SettingsDialog(r); print('theme combo default', d.theme_var.get()); d.theme_var.set('Light'); d._save(); from app import config; print('saved', config.load_config()['theme_mode']); r.destroy()"
```
Expected: prints `theme combo default Dark` (or your real saved value) then `saved light`.

- [ ] **Step 4: ruff + full suite + commit**

Run: `.venv\Scripts\python -m ruff check app/ui/settings_dialog.py ; .venv\Scripts\python -m pytest -q` → clean + green.
```bash
git add app/ui/settings_dialog.py
git commit -m "feat: add Theme (Dark/Light/System) dropdown to Settings"
```

---

### Task 6: Entry-point relaunch loop + final verification

**Files:**
- Modify: `main.py`
- Test: extend `tests/smoke/test_theme_switch.py`

- [ ] **Step 1: Write the failing test (theme actually applied from config)**

Add to `tests/smoke/test_theme_switch.py`:
```python
def test_appwindow_applies_persisted_theme_mode(monkeypatch):
    from app import config
    from app.data import db

    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None,
                 "error": "stub", "smi_gpu_name": None},
    )
    db.init_db()
    config.save_config({"theme_mode": "light"})
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    try:
        win.withdraw()
        win.update_idletasks()
        assert theme._active_variant == "light"
    finally:
        try:
            win.destroy()
        except tk.TclError:
            pass
```
(The autouse `restore_variant` fixture restores the global afterwards.)

- [ ] **Step 2: Run to verify it passes** (apply_theme already honors config from Task 2)

Run: `.venv\Scripts\python -m pytest tests/smoke/test_theme_switch.py -v`
Expected: PASS — this confirms the end-to-end config→variant wiring. (If it fails, Task 2's `apply_theme` change is missing.)

- [ ] **Step 3: Implement the relaunch loop in `main.py`**

Replace these three lines in `main()`:
```python
        win = AppWindow()
        win.mainloop()
        return 0
```
with:
```python
        # Relaunch loop: a theme change calls AppWindow.request_rebuild(), which
        # sets _rebuild_requested and destroys the window. We then construct a
        # fresh AppWindow (apply_theme re-reads theme_mode and applies the new
        # palette). Any other exit (window close) ends the loop.
        while True:
            win = AppWindow()
            win.mainloop()
            if not getattr(win, "_rebuild_requested", False):
                break
        return 0
```

- [ ] **Step 4: Full suite + ruff green**

Run: `.venv\Scripts\python -m pytest -v` → all pass (71 prior + new theme tests).
Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .` → clean.

- [ ] **Step 5: Manual verification (the real proof of the rebuild)**

Run: `H:\git\CampaignScribe\run_dev.bat`
- Settings (⚙) → Theme → **Light** → Save → window rebuilds instantly in the parchment palette; all widgets (Treeview, Listbox, Text, status dot, tabs) recolor.
- Settings → Theme → **System** → Save → matches your current OS appearance.
- Settings → Theme → **Dark** → Save → back to obsidian.
- Start a transcribe/summarize job, then try to change the theme → blocked with the "job is running" message; the choice applies on next launch.
Close the app.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/smoke/test_theme_switch.py
git commit -m "feat: relaunch loop applies theme changes by rebuilding the window"
```

---

## Self-Review (completed during planning)

- **Spec coverage (Theme Switch):**
  - Config `theme_mode ∈ {dark,light,system}`, default dark ✔ (Task 1).
  - `resolve_variant(mode)` in theme.py; `system` via darkdetect → registry → dark ✔ (Task 2); `apply_theme` reads `theme_mode` → resolves → `set_theme_variant` ✔ (Task 2).
  - Settings Theme dropdown persisting `theme_mode` ✔ (Task 5).
  - Apply via **window rebuild** (destroy + reconstruct in the same mainloop, geometry preserved) ✔ (Task 4 `request_rebuild` + Task 6 relaunch loop).
  - **Busy guard** — block switching while any tab job runs, defer to next launch ✔ (Task 4 `_any_tab_busy`/`_handle_theme_change`).
  - darkdetect dependency + fallbacks ✔ (Task 3 + `_detect_system_variant`).
  - Rebuild resets transient UI state — acceptable per spec; busy-guard prevents mid-job rebuild ✔.
  - Out of scope: live OS-theme listener (spec phase 2) — explicitly deferred.
- **Placeholder scan:** none — full code, exact tokens (`#ECE6D3`/`#0D1018`), exact registry path, exact commands.
- **Type/name consistency:** `resolve_variant`, `_detect_system_variant`, `theme_mode`, `_rebuild_requested`, `_any_tab_busy`, `request_rebuild`, `_handle_theme_change`, `_save_window_geometry`, `theme_var` used consistently across tasks/tests. `set_theme_variant` only ever receives `"dark"`/`"light"` (resolve_variant never returns `"system"`), so its validation never trips.
- **CI lanes:** `test_config_theme.py` + `test_theme_resolve.py` are Tk-free unit tests (Ubuntu lane); `test_theme_switch.py` is `@pytest.mark.gui` (Windows lane) and skips on `TclError`. `darkdetect` is not needed in CI (system-mode detection is mocked; default mode is dark) — it's an app runtime dep only.
