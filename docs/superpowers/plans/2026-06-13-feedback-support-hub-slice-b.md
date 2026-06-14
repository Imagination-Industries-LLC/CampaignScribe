# Feedback & Support Hub — Slice B (Support / Pay-What-You-Want) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, low-key way to support development — a Support section in the Feedback & Support hub, an About-box link, `FUNDING.yml` (repo Sponsor button), and one gentle one-time nudge after the 3rd consolidated summary — while being explicit that donations do NOT cover AI costs.

**Architecture:** Funding platforms are data: `support.py` holds a URL per platform and a `funding_links()` helper that yields only the configured (non-empty) ones, so adding GitHub Sponsors / Patreon later is a one-line constant change. The nudge decision is Tk-free config logic (`record_summary_and_check_nudge`) tested in isolation; the UI (`show_support_nudge`) and the summarize-tab wiring are thin. App stays fully free — no payments, no license keys.

**Tech Stack:** Python 3.11, Tkinter/ttk, pytest. Use `.venv\Scripts\python`. Windows/PowerShell 5.1.

**Spec:** `docs/superpowers/specs/2026-06-07-feedback-support-hub-design.md` (Slice B). Slice A is merged on main; this branch builds on it.

**Configured platforms (this build):** Ko-fi `ko-fi.com/campaignscribe` (live). GitHub Sponsors `Imagination-Industries-LLC` is **pending approval** — wired as an empty constant to flip on later (no broken button until then). Patreon deferred.

---

## Conventions
- `.venv\Scripts\python -m pytest ...` / `... -m ruff ...`. Tk-free unit tests on the Linux lane; GUI tests `@pytest.mark.gui` with the per-file `root` fixture (copy from `tests/gui/test_feedback_dialog.py`).
- ruff-clean before each commit; plain single-line commits, no AI attribution. UTF-8 (emoji/em-dash).
- Branch: create `feature/feedback-support-hub-slice-b` off `main` (Slice A is merged). The controller handles branch creation.

---

## Task 1: config keys, funding constants + `funding_links()`, nudge logic, FUNDING.yml (Tk-free)

**Files:**
- Modify: `app/config.py` (two new DEFAULT_CONFIG keys)
- Modify: `app/core/support.py` (funding URL constants + `funding_links()` + `record_summary_and_check_nudge()`)
- Create: `FUNDING.yml` (repo root)
- Test: `tests/unit/test_support_nudge.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_support_nudge.py
from app.core import support


def test_funding_links_includes_only_configured(monkeypatch):
    monkeypatch.setattr(support, "KOFI_URL", "https://ko-fi.com/campaignscribe")
    monkeypatch.setattr(support, "SPONSORS_URL", "")
    monkeypatch.setattr(support, "PATREON_URL", "")
    links = support.funding_links()
    assert links == [("Ko-fi", "https://ko-fi.com/campaignscribe")]


def test_funding_links_adds_sponsors_when_set(monkeypatch):
    monkeypatch.setattr(support, "KOFI_URL", "https://ko-fi.com/campaignscribe")
    monkeypatch.setattr(support, "SPONSORS_URL", "https://github.com/sponsors/Imagination-Industries-LLC")
    monkeypatch.setattr(support, "PATREON_URL", "")
    labels = [label for label, _ in support.funding_links()]
    assert labels == ["Ko-fi", "GitHub Sponsors"]


def test_nudge_fires_once_on_third_summary(monkeypatch):
    store = {"summaries_completed": 0, "support_nudge_shown": False}
    monkeypatch.setattr(support.config, "load_config", lambda: dict(store))
    monkeypatch.setattr(support.config, "save_config", lambda cfg: store.update(cfg))

    # 1st and 2nd completions: no nudge.
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 1
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 2
    # 3rd: nudge fires once, flag set.
    assert support.record_summary_and_check_nudge() is True
    assert store["summaries_completed"] == 3
    assert store["support_nudge_shown"] is True
    # 4th: never again (flag stays, counter still increments).
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 4


def test_nudge_does_not_fire_if_already_shown(monkeypatch):
    store = {"summaries_completed": 10, "support_nudge_shown": True}
    monkeypatch.setattr(support.config, "load_config", lambda: dict(store))
    monkeypatch.setattr(support.config, "save_config", lambda cfg: store.update(cfg))
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 11
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_support_nudge.py -v`
Expected: FAIL — `AttributeError: module 'app.core.support' has no attribute 'KOFI_URL'`.

- [ ] **Step 3: Implement.**

In `app/config.py` `DEFAULT_CONFIG`, add after the `voice_match_threshold` / `diarization_separation` keys:

```python
    "summaries_completed": 0,  # count of completed consolidated summaries (drives the one-time support nudge)
    "support_nudge_shown": False,  # the gentle one-time support nudge has been shown
```

In `app/core/support.py`, add a `config` import and the new members. The file currently has `from urllib.parse import quote, urlencode` and the contact/URL builders. Add at the top (after the existing imports):

```python
from app import config
```

And add the funding members + nudge logic (anywhere after the existing constants):

```python
# --- Support / Pay-What-You-Want (Slice B) ---
# Each platform is a URL; empty string = not configured (no button shown / not in FUNDING.yml).
KOFI_URL = "https://ko-fi.com/campaignscribe"
SPONSORS_URL = ""  # set to "https://github.com/sponsors/Imagination-Industries-LLC" once approved
PATREON_URL = ""  # add when a Patreon page exists

NUDGE_AFTER_SUMMARIES = 3


def funding_links() -> list[tuple[str, str]]:
    """The (label, url) pairs for the funding platforms that are configured, in display order."""
    candidates = [
        ("Ko-fi", KOFI_URL),
        ("GitHub Sponsors", SPONSORS_URL),
        ("Patreon", PATREON_URL),
    ]
    return [(label, url) for label, url in candidates if url]


def record_summary_and_check_nudge() -> bool:
    """Increment the completed-summary counter and report whether the one-time support
    nudge should be shown now (>= NUDGE_AFTER_SUMMARIES and not shown before). Sets the
    'shown' flag when it returns True, so the nudge fires at most once. Tk-free."""
    cfg = config.load_config()
    count = int(cfg.get("summaries_completed", 0)) + 1
    cfg["summaries_completed"] = count
    show = count >= NUDGE_AFTER_SUMMARIES and not cfg.get("support_nudge_shown", False)
    if show:
        cfg["support_nudge_shown"] = True
    config.save_config(cfg)
    return show
```

Create `FUNDING.yml` at the repo root (only the live platform; GitHub Sponsors/Patreon get added later):

```yaml
ko_fi: campaignscribe
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_support_nudge.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/core/support.py FUNDING.yml tests/unit/test_support_nudge.py
git commit -m "Support/PWYW: funding links + one-time nudge logic + FUNDING.yml"
```

---

## Task 2: Support section in the hub + nudge dialog + About link (GUI)

**Files:**
- Modify: `app/ui/feedback_dialog.py` (Support section in `FeedbackSupportDialog`; `show_support_nudge`; `maybe_show_support_nudge`)
- Modify: `app/ui/app_window.py` (`AboutDialog` Support button)
- Test: `tests/gui/test_feedback_dialog.py` (extend), `tests/gui/test_support_nudge_ui.py` (new)

- [ ] **Step 1: Write the failing tests**

Add to `tests/gui/test_feedback_dialog.py`:

```python
def test_dialog_shows_support_section_with_kofi(root, monkeypatch):
    from app.core import support
    from app.ui import feedback_dialog

    monkeypatch.setattr(support, "KOFI_URL", "https://ko-fi.com/campaignscribe")
    monkeypatch.setattr(support, "SPONSORS_URL", "")
    monkeypatch.setattr(support, "PATREON_URL", "")
    opened = []
    monkeypatch.setattr(feedback_dialog, "open_url", lambda url: opened.append(url))

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        dlg._support_buttons["Ko-fi"].invoke()
        assert opened == ["https://ko-fi.com/campaignscribe"]
    finally:
        dlg.destroy()
```

Update the existing `test_dialog_renders_four_sections` to account for the new Support section (now 5 top-level frames). Rename + change the assertion:

```python
def test_dialog_renders_all_sections(root):
    from tkinter import ttk

    from app.ui import feedback_dialog

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        frames = [w for w in dlg.winfo_children() if isinstance(w, ttk.Frame)]
        # Report, Copy diagnostics, Email, Feature ideas, Support = 5 (Support renders because Ko-fi is configured).
        assert len(frames) == 5
    finally:
        dlg.destroy()
```

New file `tests/gui/test_support_nudge_ui.py`:

```python
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


def test_maybe_show_support_nudge_respects_logic(root, monkeypatch):
    from app.ui import feedback_dialog

    shown = []
    monkeypatch.setattr(feedback_dialog, "show_support_nudge", lambda m: shown.append(m))
    monkeypatch.setattr(feedback_dialog.support, "record_summary_and_check_nudge", lambda: True)
    assert feedback_dialog.maybe_show_support_nudge(root) is True
    assert len(shown) == 1

    monkeypatch.setattr(feedback_dialog.support, "record_summary_and_check_nudge", lambda: False)
    assert feedback_dialog.maybe_show_support_nudge(root) is False
    assert len(shown) == 1  # not shown again


def test_show_support_nudge_builds_dialog(root):
    from app.ui import feedback_dialog

    feedback_dialog.show_support_nudge(root)
    root.update_idletasks()
    # A Toplevel child was created (the nudge); clean it up.
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops
    for w in tops:
        w.destroy()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_feedback_dialog.py tests/gui/test_support_nudge_ui.py -v`
Expected: FAIL — `_support_buttons` / `show_support_nudge` / `maybe_show_support_nudge` don't exist; the renamed section test fails on count.

- [ ] **Step 3: Implement.**

In `app/ui/feedback_dialog.py`, in `FeedbackSupportDialog.__init__`, AFTER the "Feature ideas" section and BEFORE the Close button, add the Support section (rendered only when funding is configured), and record the buttons for testing:

```python
        # Support development (Slice B): a button per configured funding platform.
        self._support_buttons: dict = {}
        links = support.funding_links()
        if links:
            sup = ttk.Frame(self)
            sup.pack(fill="x", padx=16, pady=8)
            ttk.Label(sup, text="❤️  Support development").pack(anchor="w")
            ttk.Label(
                sup,
                text=(
                    "CampaignScribe is free and open. Donations support ongoing development "
                    "only — they do not cover AI model or API costs (you pay your AI provider "
                    "directly; local and other low-cost model options are on the roadmap)."
                ),
                style=LBL_DIM,
                wraplength=500,
            ).pack(anchor="w")
            sup_btns = ttk.Frame(sup)
            sup_btns.pack(anchor="w", pady=4)
            for label, url in links:
                btn = ttk.Button(
                    sup_btns, text=label, style=BTN_GHOST, command=lambda u=url: open_url(u)
                )
                btn.pack(side="left", padx=(0, 6))
                self._support_buttons[label] = btn
```

Add the nudge functions at module level (after the class):

```python
def show_support_nudge(master) -> None:
    """The gentle one-time support nudge dialog (Support / Maybe later / Don't show again).
    The 'shown' flag is set by support.record_summary_and_check_nudge before this is called,
    so every close path means it never appears again."""
    win = tk.Toplevel(master)
    win.title("Support CampaignScribe")
    win.transient(master)
    win.grab_set()
    ttk.Label(win, text="Enjoying CampaignScribe?", style=LBL_TITLE).pack(padx=20, pady=(16, 6))
    ttk.Label(
        win,
        text=(
            "It's free and open. If it's saved you time at the table, a one-time $5/$10 helps "
            "development. (This doesn't cover AI costs.)"
        ),
        wraplength=360,
        justify="center",
        style=LBL_DIM,
    ).pack(padx=20)
    row = ttk.Frame(win)
    row.pack(pady=14)

    def _support():
        win.destroy()
        FeedbackSupportDialog(master)

    ttk.Button(row, text="Support", style=BTN_GHOST, command=_support).pack(side="left", padx=4)
    ttk.Button(row, text="Maybe later", style=BTN_GHOST, command=win.destroy).pack(side="left", padx=4)
    ttk.Button(row, text="Don't show again", style=BTN_GHOST, command=win.destroy).pack(
        side="left", padx=4
    )
    win.update_idletasks()


def maybe_show_support_nudge(master) -> bool:
    """Show the support nudge if it is due now. Returns whether it was shown. Best-effort."""
    if not support.record_summary_and_check_nudge():
        return False
    show_support_nudge(master)
    return True
```

In `app/ui/app_window.py` `AboutDialog.__init__`, add a Support button just before the existing Close button (`ttk.Button(self, text="Close", command=self.destroy).pack(pady=12)`). Replace that Close line with:

```python
        def _support():
            from app.ui.feedback_dialog import FeedbackSupportDialog

            FeedbackSupportDialog(master)

        btnrow = ttk.Frame(self)
        btnrow.pack(pady=12)
        ttk.Button(btnrow, text="❤️ Support", command=_support).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Close", command=self.destroy).pack(side="left", padx=4)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/gui/test_feedback_dialog.py tests/gui/test_support_nudge_ui.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/feedback_dialog.py app/ui/app_window.py tests/gui/test_feedback_dialog.py tests/gui/test_support_nudge_ui.py
git commit -m "Support/PWYW: hub Support section, one-time nudge dialog, About link"
```

---

## Task 3: Wire the nudge into summary consolidation + verification

**Files:**
- Modify: `app/ui/summarize_tab.py` (`_consolidate` worker success path)
- Test: full suite

- [ ] **Step 1: Implement the wiring.**

In `app/ui/summarize_tab.py`, in the `_consolidate` `worker()` function, the success path currently ends (around lines 509-515) with the status set + the optional `db.update_session(...)`. Right after the `if self.session_id:` block (still inside the `try`, after a successful save), schedule the nudge on the main thread:

```python
                if self.session_id:
                    db.update_session(
                        self.session_id,
                        summary_path=out_path,
                        status="summarized",
                    )
                # One-time support nudge (Slice B) — main thread, best-effort, never disrupts the summary.
                self.after(0, lambda: self._maybe_support_nudge())
```

Add the method on the tab (near `_consolidate`):

```python
    def _maybe_support_nudge(self) -> None:
        try:
            from app.ui.feedback_dialog import maybe_show_support_nudge

            maybe_show_support_nudge(self)
        except Exception:  # noqa: BLE001 - the nudge must never disrupt the summary flow
            pass
```

- [ ] **Step 2: Run a focused check that the wiring imports cleanly**

Run: `.venv\Scripts\python -c "import app.ui.summarize_tab"`
Expected: no error.

- [ ] **Step 3: Full suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all green (prior 222 + new tests; 0 failures).

- [ ] **Step 4: Lint + format**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/ui/summarize_tab.py
git commit -m "Summarize: show the one-time support nudge after a successful consolidation"
```

---

## Manual validation (USER, after the build)
1. Help → Feedback & Support → the **Support development** section appears with a **Ko-fi** button (opens ko-fi.com/campaignscribe) and the AI-cost disclaimer.
2. About box → **❤️ Support** opens the hub.
3. The repo shows a **Sponsor** button (from `FUNDING.yml` → Ko-fi).
4. The nudge: with `summaries_completed` near 3 in config, completing a consolidated summary shows the one-time nudge; it does not reappear on later summaries (verify `support_nudge_shown` is persisted). (Quick way to test: set `summaries_completed` to 2 in `%APPDATA%\CampaignScribe\config.json`, run one consolidation.)

## Self-review notes (against the spec, Slice B)
- Spec "FUNDING.yml (ko_fi/github/patreon)" → Task 1 (Ko-fi now; Sponsors/Patreon are one-line additions via the constants). ✓
- Spec "Support section: free-and-open + disclaimer + platform buttons" → Task 2 (`funding_links()`-driven). ✓
- Spec "About-box Support link" → Task 2. ✓
- Spec "one-time nudge after 3rd summary; Support/Maybe later/Don't show again; `summaries_completed` + `support_nudge_shown`; never repeats" → Tasks 1 (logic) + 2 (dialog) + 3 (wiring). ✓
- Spec "honest AI-cost disclaimer" → Task 2 wording (adjusted to match reality: local/low-cost options are on the roadmap, not yet shipped). ✓
- GitHub Sponsors (pending) and Patreon (deferred) are wired as empty constants — no broken buttons; flip on by setting the URL. ✓
