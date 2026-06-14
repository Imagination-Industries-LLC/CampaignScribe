# Feedback & Support Hub — Slice C (Opt-in Crash Reporting) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in (default-off), PII-scrubbed crash reporting via Sentry — a Settings checkbox that, when enabled, sends scrubbed unhandled-exception reports (main + worker threads) to help fix bugs; disabling stops all transmission.

**Architecture:** A Tk-free `app/core/crash_reporting.py` owns everything Sentry: a pure `before_send` scrubber (deep-scrubs every string via the Slice-A `diagnostics.scrub`, drops hostname/user identity) unit-tested without sentry-sdk, plus thin `init/set_enabled/capture` that lazy-import sentry-sdk and no-op when it's absent or the DSN is empty. `main.py` inits from config at startup; the Settings checkbox toggles it live; `config.log_exception` (the app's central error sink) also routes to Sentry so handled-and-logged errors are captured too.

**Tech Stack:** Python 3.11, sentry-sdk (~2.x), Tkinter/ttk, pytest. Use `.venv\Scripts\python`. Windows/PowerShell 5.1.

**Spec:** `docs/superpowers/specs/2026-06-07-feedback-support-hub-design.md` (Slice C). Slices A + B are merged on main.

**Controller gate:** before merge, the controller embeds the real Sentry write-only DSN into `crash_reporting.DSN` (placeholder `""` until then — with an empty DSN, reporting always no-ops even if the box is checked, so this is safe to build and ship-gated on the swap).

---

## Conventions
- `.venv\Scripts\python -m pytest ...` / `... -m ruff ...`. Tk-free unit tests (Task 1) on the Linux lane; the scrubber + guard tests MUST NOT require sentry-sdk to be importable (they mock it). GUI tests `@pytest.mark.gui` with the per-file `root` fixture.
- ruff-clean before each commit; plain single-line commits, no AI attribution.
- Branch: `feature/feedback-support-hub-slice-c` off `main` (controller creates it).

---

## Task 1: `app/core/crash_reporting.py` — scrubber + init/capture (Tk-free)

**Files:**
- Create: `app/core/crash_reporting.py`
- Modify: `app/config.py` (one DEFAULT_CONFIG key)
- Modify: `requirements.txt` (add sentry-sdk)
- Test: `tests/unit/test_crash_reporting.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_crash_reporting.py
import json
import types

from app.core import crash_reporting


def test_before_send_scrubs_paths_and_emails_and_drops_identity():
    event = {
        "server_name": "MIKE-DESKTOP",
        "user": {"id": "mike", "username": "mike"},
        "exception": {
            "values": [
                {
                    "value": r"boom at C:\Users\mike\AppData\x.log contact bob@example.com",
                    "stacktrace": {"frames": [{"abs_path": r"C:\Users\mike\app\y.py"}]},
                }
            ]
        },
    }
    out = crash_reporting.before_send(event, {})
    assert "server_name" not in out
    assert "user" not in out
    dumped = json.dumps(out)
    assert "mike" not in dumped          # home path + identity scrubbed/removed
    assert "bob@example.com" not in dumped
    assert "~" in dumped                 # path replaced with ~


def test_init_noop_when_disabled():
    assert crash_reporting.init(False) is False


def test_init_noop_when_dsn_empty(monkeypatch):
    monkeypatch.setattr(crash_reporting, "DSN", "")
    assert crash_reporting.init(True) is False


def test_init_noop_when_sentry_absent(monkeypatch):
    monkeypatch.setattr(crash_reporting, "DSN", "https://k@o1.ingest.sentry.io/1")
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: None)
    assert crash_reporting.init(True) is False


def test_init_calls_sentry_with_scrubber(monkeypatch):
    calls = {}
    fake = types.SimpleNamespace(init=lambda **kw: calls.update(kw))
    monkeypatch.setattr(crash_reporting, "DSN", "https://k@o1.ingest.sentry.io/1")
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: fake)
    crash_reporting._initialized = False
    assert crash_reporting.init(True) is True
    assert calls["dsn"].startswith("https://")
    assert calls["before_send"] is crash_reporting.before_send
    assert calls["include_local_variables"] is False
    assert calls["send_default_pii"] is False
    crash_reporting._initialized = False  # reset for other tests


def test_capture_noop_when_not_initialized():
    crash_reporting._initialized = False
    crash_reporting.capture(ValueError("x"))  # must not raise


def test_capture_sends_when_initialized(monkeypatch):
    sent = []
    fake = types.SimpleNamespace(capture_exception=lambda e: sent.append(e))
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: fake)
    crash_reporting._initialized = True
    err = ValueError("boom")
    crash_reporting.capture(err)
    assert sent == [err]
    crash_reporting._initialized = False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_crash_reporting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.crash_reporting'`.

- [ ] **Step 3: Implement `app/core/crash_reporting.py`**

```python
"""Opt-in (default-off), PII-scrubbed crash reporting via Sentry.

Nothing is sent unless the user enables it in Settings AND a DSN is embedded.
The before_send scrubber deep-scrubs every string in the event (home paths -> ~,
emails removed, via diagnostics.scrub) and drops hostname/user identity. sentry-sdk
is imported lazily, so the app runs normally when it is absent. Tk-free.
"""

from __future__ import annotations

# CONTROLLER: embed the Sentry write-only DSN before release. Empty => never reports.
DSN = ""

# Keys whose values can carry identity; dropped wherever they appear in the event.
_DROP_KEYS = {"server_name", "user"}

_initialized = False


def _sentry():
    """Return the sentry_sdk module, or None if it isn't installed."""
    try:
        import sentry_sdk

        return sentry_sdk
    except Exception:
        return None


def _scrub_value(value, scrub):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v, scrub) for k, v in value.items() if k not in _DROP_KEYS}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v, scrub) for v in value]
    return value


def before_send(event, hint=None):
    """Sentry before_send hook: deep-scrub strings + drop identity keys. Returns the
    scrubbed event (never None — we still send the scrubbed crash)."""
    try:
        from app.core.diagnostics import scrub

        return _scrub_value(event, scrub)
    except Exception:
        # If scrubbing itself fails, drop the event rather than risk leaking PII.
        return None


def init(enabled: bool) -> bool:
    """Initialize Sentry if enabled, a DSN is embedded, and sentry-sdk is present.
    Returns whether reporting is now active. No-op (False) otherwise."""
    global _initialized
    if not enabled or not DSN:
        return False
    sdk = _sentry()
    if sdk is None:
        return False
    sdk.init(
        dsn=DSN,
        before_send=before_send,
        include_local_variables=False,  # never capture stack-frame locals (could hold user data)
        send_default_pii=False,
        traces_sample_rate=0.0,
    )
    _initialized = True
    return True


def init_from_config() -> bool:
    """Init from the persisted opt-in flag (called at startup)."""
    from app import config

    return init(bool(config.load_config().get("crash_reporting_enabled", False)))


def set_enabled(enabled: bool) -> None:
    """Apply a live toggle from Settings: start reporting, or stop all transmission."""
    if enabled:
        init(True)
    else:
        shutdown()


def shutdown() -> None:
    """Stop all transmission immediately (revoke consent)."""
    global _initialized
    if not _initialized:
        return
    sdk = _sentry()
    if sdk is not None:
        try:
            sdk.flush(timeout=2.0)
            client = sdk.get_client()
            if client is not None:
                client.close()
        except Exception:
            pass
    _initialized = False


def capture(exc: BaseException) -> None:
    """Send a (scrubbed, via before_send) exception if reporting is active. Best-effort."""
    if not _initialized:
        return
    sdk = _sentry()
    if sdk is not None:
        try:
            sdk.capture_exception(exc)
        except Exception:
            pass
```

In `app/config.py` `DEFAULT_CONFIG`, add (after `support_nudge_shown`):
```python
    "crash_reporting_enabled": False,  # opt-in (default off) Sentry crash reporting
```

In `requirements.txt`, add a line (the app ships sentry-sdk; it's pure-python, low-risk):
```
sentry-sdk~=2.20
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_crash_reporting.py -v`
Expected: PASS (7 tests). (They mock `_sentry`, so sentry-sdk need not be installed to pass.)

- [ ] **Step 5: Commit**

```bash
git add app/core/crash_reporting.py app/config.py requirements.txt tests/unit/test_crash_reporting.py
git commit -m "Crash reporting: opt-in Sentry init + PII-scrubbing before_send"
```

---

## Task 2: Wire it up — Settings checkbox, startup init, log_exception routing

**Files:**
- Modify: `app/ui/settings_dialog.py` (a Crash-reporting checkbox + save + live toggle)
- Modify: `main.py` (init from config at startup)
- Modify: `app/config.py` `log_exception` (route to `crash_reporting.capture`)
- Test: `tests/gui/test_settings_crash_reporting.py` (new), `tests/unit/test_log_exception_routes.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_log_exception_routes.py
from app import config


def test_log_exception_routes_to_crash_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_error_log_path", lambda: tmp_path / "errors.log")
    captured = []
    from app.core import crash_reporting

    monkeypatch.setattr(crash_reporting, "capture", lambda exc: captured.append(exc))
    err = ValueError("boom")
    config.log_exception("ctx", err)
    assert captured == [err]
```

```python
# tests/gui/test_settings_crash_reporting.py
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


def test_crash_checkbox_defaults_off_and_saves(root, monkeypatch):
    from app import config
    from app.core import crash_reporting
    from app.ui import settings_dialog

    toggled = []
    monkeypatch.setattr(crash_reporting, "set_enabled", lambda v: toggled.append(v))

    dlg = settings_dialog.SettingsDialog(root)
    try:
        assert dlg.crash_var.get() is False  # default off
        dlg.crash_var.set(True)
        dlg._save()
        assert config.load_config().get("crash_reporting_enabled") is True
        assert toggled[-1] is True  # live toggle applied
    finally:
        try:
            dlg.destroy()
        except tk.TclError:
            pass  # _save may already have closed it
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_log_exception_routes.py tests/gui/test_settings_crash_reporting.py -v`
Expected: FAIL — `log_exception` doesn't call capture; `SettingsDialog` has no `crash_var`.

- [ ] **Step 3: Implement.**

(a) `app/config.py` `log_exception` — read the current method (around line 125). It writes the traceback to errors.log and returns the path. Add a best-effort capture just before the `return str(log_path)`:
```python
    try:
        from app.core import crash_reporting

        crash_reporting.capture(exc)
    except Exception:
        pass
    return str(log_path)
```

(b) `main.py` — in `main()`, after `_db.init_db()` and before importing/constructing `AppWindow`, init crash reporting from config:
```python
        _db.init_db()
        from app.core import crash_reporting

        crash_reporting.init_from_config()
        from app.ui.app_window import AppWindow
```

(c) `app/ui/settings_dialog.py` — add a Privacy/crash-reporting section. After the Discovery section (after the discovery-sample row, before `btn_frame = ttk.Frame(self)` around line 133), insert:
```python
        # ---- Privacy / crash reporting ----
        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 2)
        )
        row += 1
        ttk.Label(self, text="— Privacy —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4)
        )
        row += 1
        self.crash_var = tk.BooleanVar(value=bool(cfg.get("crash_reporting_enabled", False)))
        ttk.Checkbutton(
            self,
            text="Send anonymous crash reports to help fix bugs (opt-in)",
            variable=self.crash_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 2))
        row += 1
        ttk.Label(
            self,
            text=(
                "Off by default. Reports are scrubbed of transcripts, audio, keys, speaker "
                "profiles, and personal paths before sending. See Help → Privacy & Data."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))
        row += 1
```
(`cfg` is already loaded near the top of `__init__` — confirm the local name by reading the method; it's used as `cfg.get(...)` throughout.)

In `_save`, after the existing `config.save_config(cfg)` line (line 169), persist + apply the toggle:
```python
            cfg["crash_reporting_enabled"] = bool(self.crash_var.get())
            config.save_config(cfg)
            from app.core import crash_reporting

            crash_reporting.set_enabled(cfg["crash_reporting_enabled"])
```
(Add `cfg["crash_reporting_enabled"] = ...` alongside the other `cfg[...] =` assignments BEFORE `config.save_config(cfg)`, and the `set_enabled` call AFTER the save. Read `_save` to place these correctly — there must be exactly one `save_config(cfg)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_log_exception_routes.py tests/gui/test_settings_crash_reporting.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py main.py app/ui/settings_dialog.py tests/unit/test_log_exception_routes.py tests/gui/test_settings_crash_reporting.py
git commit -m "Crash reporting: Settings opt-in toggle, startup init, log_exception routing"
```

---

## Task 3: Privacy docs + full verification

**Files:**
- Modify: `PRIVACY.md` (update the crash-reports section — it's no longer "planned")

- [ ] **Step 1: Update PRIVACY.md.** The file has an "Optional crash reports (off by default)" section with a "*Note: opt-in crash reporting is planned and not active in the current release.*" line. Replace that section's body + drop the "planned/not active" note:

```markdown
## Optional crash reports (off by default)
- **Off unless you turn it on** in Settings → Privacy. When enabled, only *crash* reports (unhandled errors) are sent, via Sentry, to help fix bugs.
- Every report is **scrubbed before sending**: no transcripts, audio, API keys/tokens, or speaker profiles; file paths have your home folder replaced with `~`, email addresses are removed, and your computer/account name is dropped. Stack-frame local variables are never collected.
- Turning the setting back off **stops all transmission** immediately.
```

(The in-app Help → Privacy & Data dialog renders `PRIVACY.md`, so this updates both.)

- [ ] **Step 2: Full suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all green (prior total + the new crash-reporting tests; 0 failures).

- [ ] **Step 3: Lint + format**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add PRIVACY.md
git commit -m "Privacy: document the opt-in crash reporter (active, scrubbed, revocable)"
```

---

## Manual validation (USER, after the build + DSN embedded)
1. Settings → Privacy shows the unchecked "Send anonymous crash reports (opt-in)" box.
2. Help → Privacy & Data reflects the updated crash-reports text.
3. With the box OFF: force an error → nothing appears in your Sentry project.
4. With the box ON: force an error (e.g., a deliberately bad transcribe) → a scrubbed event appears in Sentry; verify the payload has NO transcript/key/path-with-username/email (home shown as `~`), and a worker-thread error is captured too.
5. Turn it back OFF → no further events.

## Self-review notes (against the spec, Slice C)
- Spec "Settings checkbox, default off, `crash_reporting_enabled`" → Tasks 1 (key) + 2 (checkbox). ✓
- Spec "sentry-sdk init only when opted in; embedded DSN; unhandled main + worker threads" → Task 1 `init` (Sentry default integrations install the excepthook + ThreadingIntegration → worker threads covered) + Task 2 startup init. The DSN is a controller-swapped placeholder. ✓
- Spec "before_send scrubber strips PII (no transcript/audio/keys/speakers; home→~; drop usernames/emails)" → Task 1 `before_send`/`_scrub_value` (deep-scrub via diagnostics.scrub + drop server_name/user + no local variables). ✓
- Spec "alongside the existing config.log_exception" → Task 2 routes log_exception → capture (captures handled-and-logged errors too). ✓
- Spec "consent explicit + revocable; disabling stops transmission" → `set_enabled(False)` → `shutdown()` (flush + close client). ✓
- Spec "PRIVACY.md + dialog text match the consent checkbox" → Task 3 (dialog renders PRIVACY.md). ✓
