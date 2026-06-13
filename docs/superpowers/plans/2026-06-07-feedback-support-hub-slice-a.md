# Feedback & Support Hub — Slice A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unblocked core of the unified `Help → Feedback & Support` hub: a local diagnostics bundle, Copy Diagnostics, Report a Problem (GitHub issue), Email feedback (`mailto:`), and the Discussions link.

**Architecture:** Two Tk-free core modules — `diagnostics.py` (the *content*: a scrubbed plain-text bundle) and `support.py` (the *destinations*: contact constants + URL builders) — are unit-tested in isolation. A new `app/ui/feedback_dialog.py` Toplevel composes them into the hub UI (following the existing `AboutDialog`/`PrivacyDialog` patterns), opened from a new Help-menu entry. Everything is user-initiated; nothing is transmitted by the app.

**Tech Stack:** Python 3.11, Tkinter/ttk, stdlib `platform`/`urllib.parse`/`webbrowser`, pytest. Use `.venv\Scripts\python`. Windows/PowerShell 5.1.

**Spec:** `docs/superpowers/specs/2026-06-07-feedback-support-hub-design.md` (Slice A). Slices B (support/PWYW) and C (Sentry) are separate plans.

---

## Conventions for the implementer
- Run with the venv python: `.venv\Scripts\python -m pytest ...`, `.venv\Scripts\python -m ruff ...`.
- Tk-free unit tests (Tasks 1-2) run on the Linux lane — no Tk, no ML stack. GUI tests (Task 3) are `@pytest.mark.gui` with a per-file `root` fixture that skips when there's no display (copy the fixture from `tests/gui/test_session_view_voicematch.py`).
- Follow existing patterns: dialogs subclass `tk.Toplevel` like `AboutDialog` (`app/ui/app_window.py:577`); use theme styles from `app.ui.theme`; open links with `app.ui.common.open_url`; make text read-only with `app.ui.common.make_readonly`.
- ruff-clean before each commit. Plain single-line commit messages, no AI attribution.

## Controller setup gates (handled before the relevant task — not the implementer's job)
- **Before Task 2:** the controller supplies the real feedback email address for `FEEDBACK_EMAIL`.
- **Before/with Task 3 ship:** the controller walks the owner through enabling GitHub Discussions on the repo (+ a Feedback/Ideas category) so the Discussions button resolves.

---

## Task 1: `app/core/diagnostics.py` — bundle + scrubber (Tk-free)

**Files:**
- Create: `app/core/diagnostics.py`
- Test: `tests/unit/test_diagnostics.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_diagnostics.py
from app.core import diagnostics


def test_scrub_replaces_user_home_with_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\alice")
    text = r"error at C:\Users\alice\AppData\Roaming\CampaignScribe\errors.log"
    out = diagnostics.scrub(text)
    assert r"C:\Users\alice" not in out
    assert "~" in out


def test_scrub_drops_email_addresses():
    out = diagnostics.scrub("contact bob.smith@example.com for help")
    assert "bob.smith@example.com" not in out
    assert "@" not in out or "example.com" not in out


def test_bundle_has_version_os_gpu(monkeypatch):
    monkeypatch.setattr(diagnostics, "_gpu_state", lambda: "GPU: none (CPU mode)")
    out = diagnostics.build_diagnostics_bundle(include_log_tail=False)
    from app import __version__

    assert f"CampaignScribe {__version__}" in out
    assert "OS:" in out
    assert "Python:" in out
    assert "GPU: none (CPU mode)" in out


def test_bundle_includes_log_tail_when_asked(monkeypatch, tmp_path):
    log = tmp_path / "errors.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: log)
    out = diagnostics.build_diagnostics_bundle(include_log_tail=True)
    assert "line 499" in out          # tail is present
    assert "line 0" not in out        # head is trimmed (only last ~200 lines)


def test_bundle_log_tail_absent_when_no_log(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: tmp_path / "missing.log")
    out = diagnostics.build_diagnostics_bundle(include_log_tail=True)
    assert "errors.log" in out  # a "(no errors.log)" note, not a crash


def test_email_header_is_compact_no_log(monkeypatch, tmp_path):
    log = tmp_path / "errors.log"
    log.write_text("SECRET LINE\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: log)
    header = diagnostics.build_email_header()
    assert "SECRET LINE" not in header  # email header never includes the log
    from app import __version__

    assert __version__ in header
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_diagnostics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.diagnostics'`.

- [ ] **Step 3: Implement `app/core/diagnostics.py`**

```python
"""User-initiated diagnostics bundle for the Feedback & Support hub.

Builds a single scrubbed, non-sensitive plain-text block (version / OS / GPU,
optionally the tail of errors.log). Deliberately excludes transcripts, audio,
API keys/tokens, and speakers.json. Tk-free.
"""

from __future__ import annotations

import os
import platform
import re

from app import __version__, config

LOG_TAIL_LINES = 200


def scrub(text: str) -> str:
    """Defense-in-depth PII scrub: user home -> ~, drop email addresses."""
    if not text:
        return text
    out = text
    # Replace the real user home and any C:\Users\<name> style paths with ~.
    home = os.path.expanduser("~")
    if home and home != "~":
        out = out.replace(home, "~")
    out = re.sub(r"[A-Za-z]:\\Users\\[^\\\/\s]+", "~", out)
    out = re.sub(r"/home/[^/\s]+", "~", out)
    # Drop email addresses.
    out = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email removed]", out)
    return out


def _gpu_state() -> str:
    """One-line GPU/torch summary from transcriber.check_gpu() (best-effort)."""
    try:
        from app.core.transcriber import check_gpu

        g = check_gpu()
        if g.get("cuda_available"):
            return f"GPU: {g.get('device_name')} ({g.get('vram_gb')} GB) · torch {g.get('torch_version')} · CUDA {g.get('torch_cuda_version')}"
        return f"GPU: none/CPU ({g.get('recommendation')}) · torch {g.get('torch_version')}"
    except Exception:
        return "GPU: unavailable"


def _log_tail() -> str:
    try:
        path = config.get_error_log_path()
        if not path.exists():
            return "(no errors.log)"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-LOG_TAIL_LINES:]
        return "\n".join(tail) if tail else "(errors.log is empty)"
    except Exception as e:  # noqa: BLE001 - diagnostics must never crash the app
        return f"(could not read errors.log: {e})"


def _header_lines() -> list[str]:
    return [
        f"CampaignScribe {__version__}",
        f"OS: {platform.platform()}",
        f"Python: {platform.python_version()}",
        _gpu_state(),
    ]


def build_email_header() -> str:
    """Compact, log-free build-info header for the mailto: body (length-limited)."""
    return scrub("\n".join(_header_lines()))


def build_diagnostics_bundle(include_log_tail: bool = True) -> str:
    """Full diagnostics block for Copy Diagnostics / Report a Problem."""
    parts = list(_header_lines())
    if include_log_tail:
        parts.append("")
        parts.append("--- errors.log (tail) ---")
        parts.append(_log_tail())
    return scrub("\n".join(parts))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_diagnostics.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/diagnostics.py tests/unit/test_diagnostics.py
git commit -m "Diagnostics: scrubbed local bundle (version/OS/GPU + errors.log tail)"
```

---

## Task 2: `app/core/support.py` — contact constants + URL builders (Tk-free)

> **CONTROLLER GATE:** before this task, the controller substitutes the real feedback address into `FEEDBACK_EMAIL` (replace the `feedback@…` placeholder value below with the owner-provided address).

**Files:**
- Create: `app/core/support.py`
- Test: `tests/unit/test_support_links.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_support_links.py
from urllib.parse import parse_qs, urlsplit

from app.core import support


def test_discussions_url_points_at_repo():
    assert support.discussions_url() == (
        "https://github.com/Imagination-Industries-LLC/CampaignScribe/discussions"
    )


def test_new_issue_url_encodes_title_and_body():
    url = support.new_issue_url("Crash on save", "line1\nline2 & more")
    assert url.startswith(
        "https://github.com/Imagination-Industries-LLC/CampaignScribe/issues/new?"
    )
    q = parse_qs(urlsplit(url).query)
    assert q["title"] == ["Crash on save"]
    assert q["body"] == ["line1\nline2 & more"]


def test_mailto_url_encodes_subject_and_body():
    url = support.mailto_url("Feedback (v1.0.0)", "header\n\n— your feedback —")
    assert url.startswith("mailto:")
    assert support.FEEDBACK_EMAIL in url
    q = parse_qs(urlsplit(url).query)
    assert q["subject"] == ["Feedback (v1.0.0)"]
    assert "— your feedback —" in q["body"][0]


def test_issue_url_overflow_helper():
    assert support.issue_url_too_long("x" * (support.MAX_ISSUE_URL + 1)) is True
    assert support.issue_url_too_long("x" * 10) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_support_links.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.support'`.

- [ ] **Step 3: Implement `app/core/support.py`**

```python
"""External-contact constants + URL builders for the Feedback & Support hub.

The single home for "where things go": the feedback address, the repo, and the
GitHub/mailto URL builders. Pure string/urllib — Tk-free. (Funding URLs are
added here in Slice B.)
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

# CONTROLLER: replace with the owner-provided public feedback address.
FEEDBACK_EMAIL = "feedback@example.com"

REPO_SLUG = "Imagination-Industries-LLC/CampaignScribe"

# GitHub rejects very long issue URLs; above this we fall back to the clipboard.
MAX_ISSUE_URL = 7000


def discussions_url() -> str:
    return f"https://github.com/{REPO_SLUG}/discussions"


def new_issue_url(title: str, body: str) -> str:
    return f"https://github.com/{REPO_SLUG}/issues/new?" + urlencode(
        {"title": title, "body": body}
    )


def issue_url_too_long(url: str) -> bool:
    return len(url) > MAX_ISSUE_URL


def mailto_url(subject: str, body: str) -> str:
    return f"mailto:{FEEDBACK_EMAIL}?" + urlencode({"subject": subject, "body": body}, quote_via=quote)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_support_links.py -v`
Expected: PASS (4 tests). (The `test_mailto_url` assertion on `FEEDBACK_EMAIL` is value-agnostic, so it passes whatever address the controller set.)

- [ ] **Step 5: Commit**

```bash
git add app/core/support.py tests/unit/test_support_links.py
git commit -m "Support: external-contact constants + GitHub/mailto URL builders"
```

---

## Task 3: `app/ui/feedback_dialog.py` — the hub dialog + Help menu wiring (GUI)

**Files:**
- Create: `app/ui/feedback_dialog.py`
- Modify: `app/ui/app_window.py` (Help menu entry + `_show_feedback`)
- Test: `tests/gui/test_feedback_dialog.py` (new, `@pytest.mark.gui`)

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_feedback_dialog.py
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


def test_dialog_opens_with_actions(root, monkeypatch):
    from app.ui import feedback_dialog

    opened = []
    monkeypatch.setattr(feedback_dialog, "open_url", lambda url: opened.append(url))

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        # Email feedback opens a mailto: with the build-info header.
        dlg._email_feedback()
        assert opened and opened[-1].startswith("mailto:")
        # Discussions opens the repo discussions page.
        dlg._open_discussions()
        assert opened[-1].endswith("/discussions")
        # Report a problem opens a GitHub new-issue URL (short bundle -> direct URL).
        dlg._report_problem()
        assert "/issues/new?" in opened[-1]
    finally:
        dlg.destroy()


def test_report_problem_overflow_uses_clipboard(root, monkeypatch):
    from app.core import diagnostics
    from app.ui import feedback_dialog

    opened = []
    monkeypatch.setattr(feedback_dialog, "open_url", lambda url: opened.append(url))
    # The overflow path shows a (blocking) info box — stub it so the test doesn't hang.
    monkeypatch.setattr(feedback_dialog.messagebox, "showinfo", lambda *a, **k: None)
    # Force an oversized bundle so the URL exceeds MAX_ISSUE_URL.
    monkeypatch.setattr(diagnostics, "build_diagnostics_bundle", lambda **k: "X" * 9000)

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        dlg._report_problem()
        # Falls back: opens a blank new-issue (no giant body) and the bundle is on the clipboard.
        assert "/issues/new?" in opened[-1]
        assert len(opened[-1]) < 9000
        assert "X" * 9000 in dlg.clipboard_get()
    finally:
        dlg.destroy()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/gui/test_feedback_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ui.feedback_dialog'`.

- [ ] **Step 3: Implement `app/ui/feedback_dialog.py`**

Follow the `AboutDialog` pattern (`tk.Toplevel`, `transient`, `grab_set`, theme styles, centered on master). Use `app.core.diagnostics`, `app.core.support`, `app.ui.common.open_url`/`make_readonly`.

```python
"""Help -> Feedback & Support hub dialog (Slice A: report / diagnostics / email / discussions)."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core import diagnostics, support
from app.ui.common import make_readonly, open_url
from app.ui.theme import BTN_GHOST, LBL_DIM, LBL_TITLE


class FeedbackSupportDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Feedback & Support — CampaignScribe")
        self.transient(master)
        self.geometry("560x520")
        self.minsize(480, 420)
        self.grab_set()

        pad = {"padx": 16, "pady": 6}
        ttk.Label(self, text="Feedback & Support", style=LBL_TITLE).pack(anchor="w", **pad)
        ttk.Label(
            self,
            text="Everything here is optional and only sent when you choose to.",
            style=LBL_DIM,
            wraplength=500,
        ).pack(anchor="w", padx=16)

        self._section(
            "🐞  Report a problem",
            "Opens a pre-filled GitHub issue with non-sensitive diagnostics.",
            "Report a problem", self._report_problem,
        )
        self._section(
            "📋  Copy diagnostics",
            "Preview and copy local diagnostics (version, GPU, recent errors).",
            "Copy diagnostics…", self._copy_diagnostics,
        )
        self._section(
            "✉️  Email feedback",
            f"Write to {support.FEEDBACK_EMAIL}. Opens a draft with a short build-info header.",
            "Email us", self._email_feedback,
        )
        self._section(
            "💡  Feature ideas",
            "Discuss ideas and see what's planned on GitHub Discussions.",
            "Open Discussions", self._open_discussions,
        )

        ttk.Button(self, text="Close", style=BTN_GHOST, command=self.destroy).pack(pady=12)

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _section(self, title: str, desc: str, btn_text: str, command) -> None:
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=16, pady=8)
        ttk.Label(frame, text=title).pack(anchor="w")
        ttk.Label(frame, text=desc, style=LBL_DIM, wraplength=500).pack(anchor="w")
        ttk.Button(frame, text=btn_text, style=BTN_GHOST, command=command).pack(anchor="w", pady=4)

    # ---- actions ----
    def _report_problem(self) -> None:
        bundle = diagnostics.build_diagnostics_bundle(include_log_tail=True)
        body = (
            "**Steps to reproduce:**\n1. \n2. \n\n"
            "**Expected:**\n\n**Actual:**\n\n"
            "**Diagnostics:**\n```\n" + bundle + "\n```\n"
        )
        url = support.new_issue_url("Bug report", body)
        if support.issue_url_too_long(url):
            # Overflow: copy the bundle, open a blank issue with a paste placeholder.
            self.clipboard_clear()
            self.clipboard_append(bundle)
            body = (
                "**Steps to reproduce:**\n1. \n2. \n\n**Expected:**\n\n**Actual:**\n\n"
                "**Diagnostics:** (paste from your clipboard here)\n"
            )
            url = support.new_issue_url("Bug report", body)
            messagebox.showinfo(
                "Report a problem",
                "Your diagnostics were copied to the clipboard — paste them into the issue.",
                parent=self,
            )
        open_url(url)

    def _copy_diagnostics(self) -> None:
        bundle = diagnostics.build_diagnostics_bundle(include_log_tail=True)
        preview = tk.Toplevel(self)
        preview.title("Diagnostics preview")
        preview.transient(self)
        preview.geometry("620x460")
        ttk.Label(
            preview, text="This is exactly what will be shared. Nothing is sent automatically.",
            style=LBL_DIM, wraplength=580,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        txt = tk.Text(preview, wrap="word", height=18)
        txt.insert("1.0", bundle)
        make_readonly(txt)
        txt.pack(fill="both", expand=True, padx=12, pady=4)
        row = ttk.Frame(preview)
        row.pack(fill="x", padx=12, pady=8)

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(bundle)
            messagebox.showinfo("Copy diagnostics", "Copied to clipboard.", parent=preview)

        def _save():
            path = filedialog.asksaveasfilename(
                parent=preview, defaultextension=".txt",
                filetypes=[("Text file", "*.txt")], initialfile="campaignscribe-diagnostics.txt",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(bundle)

        ttk.Button(row, text="Copy to clipboard", style=BTN_GHOST, command=_copy).pack(side="left")
        ttk.Button(row, text="Save as .txt…", style=BTN_GHOST, command=_save).pack(side="left", padx=6)
        ttk.Button(row, text="Close", style=BTN_GHOST, command=preview.destroy).pack(side="right")

    def _email_feedback(self) -> None:
        from app import __version__

        subject = f"CampaignScribe Feedback (v{__version__})"
        body = diagnostics.build_email_header() + "\n\n— your feedback below —\n"
        open_url(support.mailto_url(subject, body))

    def _open_discussions(self) -> None:
        open_url(support.discussions_url())
```

In `app/ui/app_window.py`, add the Help-menu entry. The current Help menu (lines ~436-441) is:
```python
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Getting Started", command=self._show_getting_started)
        helpmenu.add_command(label="Privacy & Data", command=self._show_privacy)
        helpmenu.add_separator()
        helpmenu.add_command(label="About CampaignScribe", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
```
Change it to insert "Feedback & Support" after "Privacy & Data":
```python
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Getting Started", command=self._show_getting_started)
        helpmenu.add_command(label="Privacy & Data", command=self._show_privacy)
        helpmenu.add_command(label="Feedback & Support", command=self._show_feedback)
        helpmenu.add_separator()
        helpmenu.add_command(label="About CampaignScribe", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
```
And add the handler next to `_show_about` (line ~507):
```python
    def _show_feedback(self):
        from app.ui.feedback_dialog import FeedbackSupportDialog

        FeedbackSupportDialog(self)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/gui/test_feedback_dialog.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ui/feedback_dialog.py app/ui/app_window.py tests/gui/test_feedback_dialog.py
git commit -m "Feedback & Support hub: report a problem, copy diagnostics, email, discussions"
```

---

## Task 4: Privacy note + full verification

**Files:**
- Modify: `PRIVACY.md` (a line about the user-initiated diagnostics/feedback path)

- [ ] **Step 1: Add a privacy line**

Read `PRIVACY.md`; under its data-handling section add a sentence (match the file's existing tone/format):

> **Diagnostics & feedback (user-initiated):** The Feedback & Support menu can build a small diagnostics bundle (app version, OS, GPU info, and the tail of the local error log) and a feedback email. These are shown to you before anything leaves the app, contain no transcripts, audio, API keys, or speaker profiles, and are only sent if you choose to send them.

- [ ] **Step 2: Full suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all green (prior total + 12 new tests; 0 failures).

- [ ] **Step 3: Lint + format**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add PRIVACY.md
git commit -m "Privacy: note the user-initiated diagnostics/feedback path"
```

---

## Manual validation (USER, after the build)
1. Help → Feedback & Support opens the hub with all four sections.
2. **Copy diagnostics** → preview shows version/OS/GPU + recent error-log lines, home path shown as `~`, no transcripts/keys; Copy and Save as .txt work.
3. **Report a problem** → opens a GitHub new-issue prefilled with the template + diagnostics (or, on overflow, a blank issue with the bundle on the clipboard).
4. **Email us** → opens a mail draft to the feedback address with the build-info header + placeholder.
5. **Open Discussions** → opens the repo Discussions page (once Discussions is enabled).

## Self-review notes (against the spec, Slice A)
- Spec "one Help → Feedback & Support dialog, sections 1-4" → Task 3. ✓
- Spec "diagnostics.py bundle + scrubber, excludes sensitive, log tail ~200, compact email header" → Task 1. ✓
- Spec "Report a Problem prefilled issue + clipboard overflow fallback" → Task 3 `_report_problem`. ✓
- Spec "Email mailto with build-info header, address copyable/shown" → Task 3 `_email_feedback` + the address shown in the section text. ✓
- Spec "Discussions link" → Task 3 `_open_discussions` (+ controller enables Discussions). ✓
- Spec "support.py holds FEEDBACK_EMAIL/REPO_SLUG/URL builders" → Task 2. ✓
- Spec "privacy line for user-initiated diagnostics/feedback" → Task 4. ✓
- Slices B (support/PWYW) and C (Sentry) are out of scope for this plan.
