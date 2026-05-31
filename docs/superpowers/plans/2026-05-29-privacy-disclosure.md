# Privacy & Data-Flow Disclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disclose, in plain English, exactly what data leaves the user's machine — via a `PRIVACY.md` at the repo root, a Help → "Privacy & Data" dialog that renders it, and small muted inline notes on the four API-using tabs.

**Architecture:** A single source of truth (`PRIVACY.md`) is bundled as a PyInstaller data file and read at runtime by a Tk-free helper module (`app/core/privacy.py`), which also holds the canonical URLs and the inline-note strings. The UI layer adds a `PrivacyDialog` (mirrors the existing `AboutDialog`) and a reusable `add_privacy_note()` helper that each API tab calls. Keeping the wording in `PRIVACY.md` (not duplicated in code) satisfies the spec's "keep in-app text and PRIVACY.md in sync" requirement.

**Tech Stack:** Python 3.11, Tkinter/ttk, the existing `app.ui.theme` design system (`LBL_DIM`, `BTN_LINK`, `BTN_GHOST`), `webbrowser` (stdlib) for opening links, PyInstaller for bundling.

**Repo:** `Imagination-Industries-LLC/CampaignScribe`. Phase 1, unit 1 of 3 (Privacy → Theme → Feedback/Support Hub). Branch off `main`: `feature/privacy-disclosure`.

---

## Scope & ground rules
- This is **one** of three independent Phase 1 plans. It produces working, testable software on its own.
- **Project rules:** plain commits (NO `Co-Authored-By`/Claude attribution); no predecessor-product name references; `CREATE_NO_WINDOW` on any subprocess (none added here); ruff-clean; tests green.
- **Out of scope (deferred):** the crash-report opt-in itself (#2 / hub plan) — but `PRIVACY.md` includes the baseline "Optional crash reports (off by default)" wording now so the statement is complete; the hub plan will wire the actual toggle and must keep its consent text consistent with this file.

## File Structure
- **Create `PRIVACY.md`** (repo root) — canonical plain-English data-flow statement. Single source of truth.
- **Create `app/core/privacy.py`** — Tk-free: resolves + reads bundled `PRIVACY.md` (fallback to a short embedded statement), plus canonical URL + inline-note string constants. Unit-tested.
- **Modify `CampaignScribe.spec`** — bundle `PRIVACY.md` into the frozen app's root.
- **Modify `app/ui/common.py`** — add `open_url(url)` and `add_privacy_note(tab, text)` helpers.
- **Modify `app/ui/app_window.py`** — Help → "Privacy & Data" menu item; `_show_privacy()`; new `PrivacyDialog(tk.Toplevel)`.
- **Modify the four API tabs** (`discover_tab.py`, `transcribe_tab.py`, `refine_tab.py`, `summarize_tab.py`) — call `add_privacy_note(self, …)` at the end of `__init__`, storing the label as `self._privacy_note` (for test assertions).
- **Create `tests/unit/test_privacy.py`** and **`tests/smoke/test_privacy_dialog.py`**.

---

### Task 1: `PRIVACY.md` (canonical wording) + bundle it

**Files:**
- Create: `PRIVACY.md`
- Modify: `CampaignScribe.spec` (the `datas` list)

- [ ] **Step 1: Create `PRIVACY.md` at the repo root** with exactly this content:

```markdown
# CampaignScribe — Privacy & Data Flow

CampaignScribe is built to collect as little as possible and to be honest and explicit about where your data goes. This is a plain-English description of what stays on your computer and what is sent to outside services (and why).

## Stays on your computer (never sent anywhere)
- **Your audio recordings** — converted and transcribed locally; audio never leaves your machine.
- **The local database** (session metadata) and your saved **transcripts, summaries, and `speakers.json`**.
- **Your Anthropic API key and HuggingFace token** — stored in Windows Credential Manager; sent only to the respective service to authenticate.

## Sent to the Anthropic Claude API (and why)
- **Short transcript snippets** (speaker samples) — to identify who is speaking (Discover, Transcribe, Refine).
- **Full transcript text** — to write session summaries (Summarize).
- **Your campaign/speaker context** from `speakers.json` — as context for the above.

Anthropic states that API inputs are not used to train their models (commercial terms); API logs are retained briefly (~7–30 days) for abuse monitoring. See Anthropic's privacy policy: https://www.anthropic.com/legal/privacy

## Sent to HuggingFace
- **Only your HuggingFace token**, to authenticate and download the speaker-diarization model. No audio or transcripts are sent — diarization runs locally on your machine.

## Sent to GitHub
- **Update checks** contact GitHub to see whether a newer version exists (and to download it). No personal content.

## Optional crash reports (off by default)
- Only if you opt in. Crash reports are scrubbed of transcripts, keys, and audio before sending.

## What CampaignScribe does NOT do
- No analytics, no tracking, no telemetry by default, and no servers of our own. We collect nothing about you.
```

- [ ] **Step 2: Bundle `PRIVACY.md` in the PyInstaller spec**

In `CampaignScribe.spec`, change the `datas` line:
```python
datas = [('ffmpeg\\ffmpeg.exe', 'ffmpeg'), ('assets\\icon.ico', 'assets')]
```
to:
```python
datas = [('ffmpeg\\ffmpeg.exe', 'ffmpeg'), ('assets\\icon.ico', 'assets'), ('PRIVACY.md', '.')]
```

- [ ] **Step 3: Commit**

```bash
git add PRIVACY.md CampaignScribe.spec
git commit -m "docs: add PRIVACY.md data-flow statement and bundle it in the build"
```

---

### Task 2: `app/core/privacy.py` (Tk-free loader + constants)

**Files:**
- Create: `app/core/privacy.py`
- Test: `tests/unit/test_privacy.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for app.core.privacy: PRIVACY.md loader, fallback, and constants."""
from __future__ import annotations

from app.core import privacy


def test_load_privacy_text_reads_repo_privacy_md():
    text = privacy.load_privacy_text()
    assert "Stays on your computer" in text
    assert "Anthropic Claude API" in text
    assert "does NOT" in text or "What CampaignScribe does NOT do" in text


def test_load_privacy_text_matches_repo_file():
    # The dialog's single source of truth IS PRIVACY.md.
    from pathlib import Path

    repo_md = Path(privacy.__file__).resolve().parents[2] / "PRIVACY.md"
    assert repo_md.exists()
    assert privacy.load_privacy_text() == repo_md.read_text(encoding="utf-8")


def test_load_privacy_text_falls_back_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(privacy, "_privacy_md_path", lambda: tmp_path / "nope.md")
    text = privacy.load_privacy_text()
    assert "Anthropic" in text
    assert text.strip()  # non-empty embedded fallback


def test_urls_are_https():
    assert privacy.ANTHROPIC_PRIVACY_URL.startswith("https://")
    assert privacy.PRIVACY_MD_URL.startswith("https://")


def test_inline_note_strings_reference_anthropic_and_help():
    for note in (privacy.NOTE_SAMPLES, privacy.NOTE_TRANSCRIPT):
        assert "Anthropic Claude API" in note
        assert "Privacy & Data" in note
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_privacy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.privacy'`

- [ ] **Step 3: Implement `app/core/privacy.py`**

```python
"""Privacy disclosure text + constants (no Tk dependency).

PRIVACY.md (repo root) is the single source of truth; it is bundled into the
frozen app and read at runtime. A short embedded statement is used only if the
file can't be found (defensive — should not happen in a correct build).
"""

from __future__ import annotations

import sys
from pathlib import Path

ANTHROPIC_PRIVACY_URL = "https://www.anthropic.com/legal/privacy"
PRIVACY_MD_URL = "https://github.com/Imagination-Industries-LLC/CampaignScribe/blob/main/PRIVACY.md"

NOTE_SAMPLES = (
    "Speaker samples are sent to the Anthropic Claude API for this step. "
    "Learn more: Help → Privacy & Data."
)
NOTE_TRANSCRIPT = (
    "Transcript text is sent to the Anthropic Claude API for this step. "
    "Learn more: Help → Privacy & Data."
)

_FALLBACK = (
    "CampaignScribe sends short transcript snippets and full transcript text to "
    "the Anthropic Claude API to identify speakers and write summaries. Your audio, "
    "database, saved files, and API keys stay on your computer. No analytics or "
    "telemetry by default. See Help → Privacy & Data and PRIVACY.md for details."
)


def _privacy_md_path() -> Path:
    """Path to the bundled/dev PRIVACY.md."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[2]  # repo root
    return base / "PRIVACY.md"


def load_privacy_text() -> str:
    """Return the full privacy statement, or a short embedded fallback."""
    try:
        return _privacy_md_path().read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_privacy.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/privacy.py tests/unit/test_privacy.py
git commit -m "feat: add privacy text loader + constants (app.core.privacy)"
```

---

### Task 3: `common.py` helpers — `open_url` + `add_privacy_note`

**Files:**
- Modify: `app/ui/common.py`
- Test: `tests/unit/test_common_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for app.ui.common helpers: open_url + add_privacy_note."""
from __future__ import annotations

import tkinter as tk

import pytest

from app.ui import common


def test_open_url_calls_webbrowser(monkeypatch):
    opened = {}
    monkeypatch.setattr(common.webbrowser, "open", lambda url, new=0: opened.setdefault("url", url))
    common.open_url("https://example.com/x")
    assert opened["url"] == "https://example.com/x"


def test_open_url_ignores_empty(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(common.webbrowser, "open", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    common.open_url("")
    assert called["n"] == 0


@pytest.mark.gui
def test_add_privacy_note_grid_parent():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    try:
        frame = tk.Frame(root)
        tk.Label(frame, text="x").grid(row=0, column=0)  # make it grid-managed
        note = common.add_privacy_note(frame, "hello note")
        assert note.cget("text") == "hello note"
        assert note.winfo_manager() == "grid"
    finally:
        root.destroy()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/unit/test_common_helpers.py -v`
Expected: FAIL (`AttributeError: module 'app.ui.common' has no attribute 'webbrowser'` / `open_url`)

- [ ] **Step 3: Implement the helpers in `app/ui/common.py`**

Add `import webbrowser` to the imports at the top (alphabetical, after `import sys`), and add these functions (place after `reveal_in_folder`):

```python
def open_url(url: str) -> None:
    """Open a URL in the user's default browser. No-op on empty input."""
    if not url:
        return
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass


def add_privacy_note(tab: tk.Widget, text: str) -> ttk.Label:
    """Append a muted privacy one-liner to the bottom of a tab.

    Matches the tab's geometry manager: a new bottom grid row spanning all
    columns for grid-managed tabs, else packed. Returns the label."""
    from app.ui.theme import LBL_DIM, S_2, S_4

    note = ttk.Label(tab, text=text, style=LBL_DIM, wraplength=760, justify="left")
    cols, rows = tab.grid_size()
    if cols > 0:
        note.grid(row=rows, column=0, columnspan=cols, sticky="w", padx=S_4, pady=(0, S_2))
    else:
        note.pack(anchor="w", padx=S_4, pady=(0, S_2))
    return note
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_common_helpers.py -v`
Expected: PASS (gui test passes on Windows/display, skips headless)

- [ ] **Step 5: Commit**

```bash
git add app/ui/common.py tests/unit/test_common_helpers.py
git commit -m "feat: add open_url + add_privacy_note helpers to common"
```

---

### Task 4: Help → "Privacy & Data" dialog in `app_window.py`

**Files:**
- Modify: `app/ui/app_window.py` (imports; `_build_menu` helpmenu; add `_show_privacy`; add `PrivacyDialog` class)

- [ ] **Step 1: Add the imports**

In `app/ui/app_window.py`, add after the existing `from app.ui.common import ...` line:
```python
from app.core import privacy
```
And ensure `BTN_LINK` and `BTN_GHOST` are in the `from app.ui.theme import (...)` block (add `BTN_LINK` if missing; `BTN_GHOST`, `LBL_TITLE`, `LBL_EYEBROW`, `S_2`, `S_3`, `S_4`, `color` are already imported).

- [ ] **Step 2: Add the Help menu item**

In `_build_menu`, change the help menu block to insert "Privacy & Data" before About, with a separator:
```python
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Getting Started", command=self._show_getting_started)
        helpmenu.add_command(label="Privacy & Data", command=self._show_privacy)
        helpmenu.add_separator()
        helpmenu.add_command(label="About CampaignScribe", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
```

- [ ] **Step 3: Add the `_show_privacy` method**

Add next to `_show_about`:
```python
    def _show_privacy(self):
        PrivacyDialog(self)
```

- [ ] **Step 4: Add the `PrivacyDialog` class** (after `AboutDialog`)

```python
class PrivacyDialog(tk.Toplevel):
    """Scrollable Help → Privacy & Data dialog rendering PRIVACY.md."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Privacy & Data — CampaignScribe")
        self.transient(master)
        self.geometry("640x560")
        self.minsize(520, 420)
        self.grab_set()

        ttk.Label(self, text="Privacy & Data", style=LBL_TITLE).pack(
            anchor="w", padx=S_4, pady=(S_4, S_2)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=S_4)
        text = tk.Text(body, wrap="word", borderwidth=0, highlightthickness=0,
                       background=color("BG_INPUT"), foreground=color("FG"))
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", privacy.load_privacy_text())
        make_readonly(text)

        links = ttk.Frame(self)
        links.pack(fill="x", padx=S_4, pady=S_3)
        ttk.Button(
            links, text="Anthropic Privacy Policy", style=BTN_LINK,
            command=lambda: open_url(privacy.ANTHROPIC_PRIVACY_URL),
        ).pack(side="left")
        ttk.Button(
            links, text="View PRIVACY.md on GitHub", style=BTN_LINK,
            command=lambda: open_url(privacy.PRIVACY_MD_URL),
        ).pack(side="left", padx=(S_3, 0))
        ttk.Button(links, text="Close", style=BTN_GHOST, command=self.destroy).pack(side="right")

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
```

Also add `make_readonly` and `open_url` to the `from app.ui.common import (...)` import (currently `open_path_native, reveal_in_folder`):
```python
from app.ui.common import make_readonly, open_path_native, open_url, reveal_in_folder
```

- [ ] **Step 5: Verify imports + app still constructs**

Run: `.venv\Scripts\python -c "import app; from app.ui.app_window import AppWindow, PrivacyDialog; print('OK')"`
Expected: prints `OK`

- [ ] **Step 6: Commit**

```bash
git add app/ui/app_window.py
git commit -m "feat: add Help > Privacy & Data dialog rendering PRIVACY.md"
```

---

### Task 5: Inline privacy notes on the four API tabs

**Files:**
- Modify: `app/ui/discover_tab.py`, `app/ui/transcribe_tab.py`, `app/ui/refine_tab.py` (use `privacy.NOTE_SAMPLES`)
- Modify: `app/ui/summarize_tab.py` (use `privacy.NOTE_TRANSCRIPT`)

Each tab is a grid-managed `ttk.Frame` whose `__init__(self, master, app_window)` builds widgets. Add the note as the **last action** of `__init__` so it lands on a fresh bottom row.

- [ ] **Step 1: discover_tab.py** — add import `from app.core import privacy` and `from app.ui.common import add_privacy_note` (merge with any existing `from app.ui.common import ...`). At the very end of `__init__`, add:
```python
        self._privacy_note = add_privacy_note(self, privacy.NOTE_SAMPLES)
```

- [ ] **Step 2: transcribe_tab.py** — same imports; at end of `__init__`:
```python
        self._privacy_note = add_privacy_note(self, privacy.NOTE_SAMPLES)
```

- [ ] **Step 3: refine_tab.py** — same imports; at end of `__init__`:
```python
        self._privacy_note = add_privacy_note(self, privacy.NOTE_SAMPLES)
```

- [ ] **Step 4: summarize_tab.py** — same imports; at end of `__init__` (note: **transcript** wording):
```python
        self._privacy_note = add_privacy_note(self, privacy.NOTE_TRANSCRIPT)
```

- [ ] **Step 5: Verify the app constructs (no grid/pack conflict)**

Run: `.venv\Scripts\python -c "import app; from app.data import db; db.init_db(); from app.ui.app_window import AppWindow"`  — then run the smoke suite in Task 6. (A geometry-manager conflict would raise `TclError` during construction.)

- [ ] **Step 6: Commit**

```bash
git add app/ui/discover_tab.py app/ui/transcribe_tab.py app/ui/refine_tab.py app/ui/summarize_tab.py
git commit -m "feat: add inline privacy notes to the four API-using tabs"
```

---

### Task 6: Smoke test for the dialog + tab notes; full green

**Files:**
- Create: `tests/smoke/test_privacy_dialog.py`

- [ ] **Step 1: Write the smoke test**

```python
"""Headless smoke: Privacy dialog builds; the four API tabs carry a privacy note."""
from __future__ import annotations

import tkinter as tk

import pytest

from app.core import privacy

pytestmark = pytest.mark.gui


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
        win.destroy()


def test_privacy_dialog_builds_and_shows_statement(app):
    from app.ui.app_window import PrivacyDialog

    dlg = PrivacyDialog(app)
    app.update_idletasks()
    try:
        texts = [w for w in dlg.winfo_children() if isinstance(w, tk.Frame)]
        assert texts  # dialog built a body frame
    finally:
        dlg.destroy()


def test_api_tabs_have_privacy_notes(app):
    assert app.discover_tab._privacy_note.cget("text") == privacy.NOTE_SAMPLES
    assert app.transcribe_tab._privacy_note.cget("text") == privacy.NOTE_SAMPLES
    assert app.refine_tab._privacy_note.cget("text") == privacy.NOTE_SAMPLES
    assert app.summarize_tab._privacy_note.cget("text") == privacy.NOTE_TRANSCRIPT
```

- [ ] **Step 2: Run the smoke test**

Run: `.venv\Scripts\python -m pytest tests/smoke/test_privacy_dialog.py -v`
Expected: PASS (2 tests) on Windows/display; SKIP if headless.

- [ ] **Step 3: Full suite + ruff green**

Run: `.venv\Scripts\python -m pytest -v` → all pass (59 prior + new).
Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .` → clean.

- [ ] **Step 4: Launch from source to eyeball**

Run: `H:\git\CampaignScribe\run_dev.bat` — Help → Privacy & Data opens with the statement + working links; each API tab shows its muted note. Close.

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/test_privacy_dialog.py
git commit -m "test: smoke-test Privacy dialog + inline tab notes"
```

---

## Self-Review (completed during planning)

- **Spec coverage (Privacy & Data-Flow Disclosure):**
  - Help → Privacy & Data dialog ✔ (Task 4, `PrivacyDialog`) with links to Anthropic policy + repo `PRIVACY.md` ✔.
  - Inline `LBL_DIM` notes on Discover/Transcribe/Refine (samples) + Summarize (transcript) ✔ (Task 5; exact spec wording in `NOTE_SAMPLES`/`NOTE_TRANSCRIPT`).
  - `PRIVACY.md` at repo root, single source ✔ (Task 1); dialog reads it (Task 2 `load_privacy_text`) → in-app text and file can't drift (test `test_load_privacy_text_matches_repo_file`).
  - Data-flow statement content (stays-local / Anthropic / HuggingFace / GitHub / opt-in crash / "does NOT") ✔ — verbatim from the approved spec wording.
  - "Keep in sync" risk ✔ resolved by bundling + reading one file.
  - Coupling to #2 consent wording — noted; the baseline crash-report line is present for the hub plan to stay consistent with.
- **Placeholder scan:** none — full code for every file, exact spec wording, exact commands.
- **Type/name consistency:** `load_privacy_text`, `_privacy_md_path`, `ANTHROPIC_PRIVACY_URL`, `PRIVACY_MD_URL`, `NOTE_SAMPLES`, `NOTE_TRANSCRIPT`, `open_url`, `add_privacy_note`, `self._privacy_note`, `PrivacyDialog` are used consistently across tasks and tests.
- **Tk-free boundary:** `app/core/privacy.py` imports no Tk → its unit tests run on the Ubuntu CI lane; the dialog/note tests are `@pytest.mark.gui` (Windows lane), matching the CI split.
