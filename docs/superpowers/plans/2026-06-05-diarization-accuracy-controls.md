# Expected-Voice Count Control Implementation Plan (count-only, post-spike)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the session ① step's roster-derived expected-voice count into the diarization pass as an "at least N (room for one more)" speaker-count constraint, so the DM can force a missed/merged voice to appear.

**Architecture:** Pure Tk-free translation functions (`speaker_count_window`, `diarization_run_kwargs`) live in `app/core/transcriber.py`, unit-tested in isolation. `transcribe_file` takes a caller-owned `min/max_speakers` window (replacing the internal exact-lock). The ① step (`SessionView`) renders an editable pre-seeded count and threads it through the existing `open_session_stage → load_for_session` handoff (in-memory, no DB/schema change). No clustering-threshold work — the spike proved community-1's VBx threshold is inert (`docs/superpowers/notes/2026-06-05-clustering-threshold-spike.md`); board #51 is deferred.

**Tech Stack:** Python 3.11, Tkinter/ttk, whisperx 3.8 (`DiarizationPipeline`), pyannote community-1, pytest. Use `.venv\Scripts\python`. Windows/PowerShell 5.1.

**Spec:** `docs/superpowers/specs/2026-06-05-diarization-accuracy-controls-design.md`

---

## Conventions for the implementer
- Run everything with the venv python: `.venv\Scripts\python -m pytest ...`, `.venv\Scripts\python -m ruff ...`.
- Two CI lanes: **Tk-free unit tests** run on Linux (the Task 1 functions are plain Python — no numpy, no importorskip needed); **GUI tests** are `@pytest.mark.gui` (Windows lane), each using a per-file `root` fixture that skips when there is no display.
- The transcript/embedding path (Spec 2 single-pass `return_embeddings=True`) must stay byte-identical — only the `min/max_speakers` kwargs handed to the diarizer change.
- Commit messages: plain, single-line, no AI attribution. ruff-clean before every commit (`.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .`).

---

## Task 1: transcriber — caller-owned speaker-count window

**Files:**
- Modify: `app/core/transcriber.py` (add two module-level pure functions near `coerce_embeddings`; change `transcribe_file` signature + the diarization kwargs block around lines 162-202)
- Test: `tests/unit/test_transcriber_count_window.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_transcriber_count_window.py
from app.core import transcriber as tr


def test_count_window_exact_from_num_speakers():
    assert tr.speaker_count_window(num_speakers=5) == {"min_speakers": 5, "max_speakers": 5}


def test_count_window_explicit_range_wins():
    assert tr.speaker_count_window(num_speakers=5, min_speakers=4, max_speakers=6) == {
        "min_speakers": 4,
        "max_speakers": 6,
    }


def test_count_window_unconstrained_is_empty():
    assert tr.speaker_count_window() == {}
    assert tr.speaker_count_window(num_speakers=0) == {}


def test_count_window_floors_at_one():
    assert tr.speaker_count_window(min_speakers=0, max_speakers=2) == {"max_speakers": 2}


def test_run_kwargs_at_least_n_window():
    # expected_count drives "at least N, room for one more"
    assert tr.diarization_run_kwargs(5, 9) == {"min_speakers": 5, "max_speakers": 6}


def test_run_kwargs_falls_back_to_exact_count():
    assert tr.diarization_run_kwargs(0, 7) == {"num_speakers": 7}


def test_run_kwargs_floor_at_one():
    assert tr.diarization_run_kwargs(1, 5) == {"min_speakers": 1, "max_speakers": 2}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_transcriber_count_window.py -v`
Expected: FAIL with `AttributeError: module 'app.core.transcriber' has no attribute 'speaker_count_window'`.

- [ ] **Step 3: Implement in `app/core/transcriber.py`**

Add near the top of the module (after the imports / `coerce_embeddings`):

```python
def speaker_count_window(
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Build diarization min/max_speakers kwargs. Explicit min/max win; otherwise
    num_speakers (>0) locks an exact count (min=max=N). Floors at 1. {} = unconstrained."""
    lo = min_speakers if min_speakers is not None else (num_speakers if (num_speakers or 0) > 0 else None)
    hi = max_speakers if max_speakers is not None else (num_speakers if (num_speakers or 0) > 0 else None)
    out: dict[str, int] = {}
    if lo is not None and lo >= 1:
        out["min_speakers"] = int(lo)
    if hi is not None and hi >= 1:
        out["max_speakers"] = int(hi)
    return out


def diarization_run_kwargs(expected_count: int | None, fallback_count: int) -> dict:
    """Translate the UI's run-params into transcribe_file kwargs. A confirmed
    expected_count (>0) becomes an 'at least N, room for one more' window
    (min=max(1,N), max=N+1); otherwise the loose-file spinbox is used as an exact
    count. Pure / Tk-free."""
    n = int(expected_count or 0)
    if n > 0:
        return {"min_speakers": max(1, n), "max_speakers": n + 1}
    return {"num_speakers": int(fallback_count)}
```

Change `transcribe_file`'s signature (line ~162) to:

```python
    def transcribe_file(
        self,
        wav_path: str,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        progress: Callable[[str, float], None] | None = None,
    ) -> list[dict[str, Any]]:
```

Replace the diarization kwargs block (current lines ~192-195 — the `kwargs = {}` / `if num_speakers...` lines) with a single call to the helper, leaving the try/except diarization call below it unchanged:

```python
        if progress:
            progress("Diarizing speakers", 0.75)
        kwargs: dict[str, Any] = speaker_count_window(num_speakers, min_speakers, max_speakers)
        try:
            diarize_segments, _spk_emb = self._diarize(wav_path, return_embeddings=True, **kwargs)
            self._last_speaker_embeddings = coerce_embeddings(_spk_emb)
        except Exception:  # noqa: BLE001 - embeddings are best-effort; never break the transcript
            diarize_segments = self._diarize(wav_path, **kwargs)  # proven path, no embeddings
            self._last_speaker_embeddings = {}
        result = whisperx.assign_word_speakers(diarize_segments, result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_transcriber_count_window.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/transcriber.py tests/unit/test_transcriber_count_window.py
git commit -m "Diarization: caller-owned speaker-count window in transcribe_file"
```

---

## Task 2: SessionView ① — editable, pre-seeded expected-voice count

**Files:**
- Modify: `app/ui/session_view.py` (replace the read-only count label with an editable spinbox; keep it in sync; add a run-params builder)
- Test: `tests/gui/test_session_view_count.py` (new, `@pytest.mark.gui`)

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_session_view_count.py
import tkinter as tk
import types

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


def _app():
    return types.SimpleNamespace(
        notebook=None,
        open_session_stage=lambda *a, **k: None,
        open_home=lambda: None,
    )


def _campaign(name, players):
    from app.core import library, speakers_io

    slug = library.create_campaign(name)
    doc = speakers_io.profiles_to_speakers_doc(
        name,
        "",
        [{"display_name": p, "role": "Player", "include_in_tracking": 1} for p in players],
        npcs=[],
    )
    library.add_version(slug, doc)
    return slug


def test_confirm_step_has_editable_preseeded_count(root):
    from app.data import db
    from app.ui.session_view import SessionView

    db.init_db()
    slug = _campaign("Strahd", ["Ann", "Bob", "Cara"])
    sid = db.create_session("Night 1", campaign_slug=slug)
    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    try:
        # Pre-seeds from the present roster (3) and is editable.
        assert int(view.count_spin_var.get()) == 3
        view.count_spin_var.set(4)
        assert view._run_params_for_transcribe() == {"expected_count": 4}
    finally:
        view.destroy()
```

> Mirrors the proven setup in `tests/gui/test_session_view_voicematch.py` (per-file `root` fixture, `_app()` SimpleNamespace, `library.create_campaign` + `speakers_io.profiles_to_speakers_doc` + `library.add_version`, `db.create_session`). `profiles_to_speakers_doc` maps each `display_name` to the `player_name` that `SessionView._load_roster` reads, so the roster is the three players.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/gui/test_session_view_count.py -v`
Expected: FAIL with `AttributeError: 'SessionView' object has no attribute 'count_spin_var'`.

- [ ] **Step 3: Implement in `app/ui/session_view.py`**

Replace the count label (current lines 70-71):

```python
        self.count_var = tk.StringVar()
        ttk.Label(confirm_lf, textvariable=self.count_var, style=LBL_DIM).pack(anchor="w", padx=4)
```

with the live tally label plus an editable, pre-seeded spinbox:

```python
        self.count_var = tk.StringVar()
        ttk.Label(confirm_lf, textvariable=self.count_var, style=LBL_DIM).pack(anchor="w", padx=4)
        countrow = ttk.Frame(confirm_lf)
        countrow.pack(fill="x", padx=4, pady=2)
        ttk.Label(countrow, text="Expected voices for this run:").pack(side="left")
        self.count_spin_var = tk.IntVar(value=self.expected_speaker_count())
        ttk.Spinbox(countrow, from_=1, to=20, textvariable=self.count_spin_var, width=6).pack(
            side="left", padx=6
        )
```

Update `_update_count` so toggling present/absent keeps the spinbox in sync, and the label reads as a roster tally (not "Expected voices", to avoid implying the label is the value used):

```python
    def _update_count(self) -> None:
        n = self.expected_speaker_count()
        self.count_var.set(f"Present in roster: {n}")
        if hasattr(self, "count_spin_var"):
            self.count_spin_var.set(n)
```

Add the run-params builder (e.g. right after `expected_speaker_count`):

```python
    def _run_params_for_transcribe(self) -> dict:
        return {"expected_count": int(self.count_spin_var.get() or 0)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/gui/test_session_view_count.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/session_view.py tests/gui/test_session_view_count.py
git commit -m "SessionView ①: editable, roster-preseeded expected-voice count"
```

---

## Task 3: Thread the count into the transcribe run (+ loose-file fallback)

**Files:**
- Modify: `app/ui/session_view.py` (`_start_transcription` passes run-params)
- Modify: `app/ui/app_window.py` (`open_session_stage` forwards run-params)
- Modify: `app/ui/transcribe_tab.py` (`__init__` inits `_run_params`; `load_for_session` stores it; `load_session` resets it; `_worker` derives kwargs via `diarization_run_kwargs`)
- Test: `tests/gui/test_transcribe_count_handoff.py` (new, `@pytest.mark.gui`)

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_transcribe_count_handoff.py
import tkinter as tk
import types

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


def _campaign(name, players):
    from app.core import library, speakers_io

    slug = library.create_campaign(name)
    doc = speakers_io.profiles_to_speakers_doc(
        name,
        "",
        [{"display_name": p, "role": "Player", "include_in_tracking": 1} for p in players],
        npcs=[],
    )
    library.add_version(slug, doc)
    return slug


def test_start_transcription_hands_count_to_stage(root):
    from app.data import db
    from app.ui.session_view import SessionView

    db.init_db()
    slug = _campaign("Strahd", ["Ann", "Bob", "Cara"])
    sid = db.create_session("Night 1", campaign_slug=slug)

    captured = {}
    app = types.SimpleNamespace(
        notebook=None,
        open_home=lambda: None,
        open_session_stage=lambda s, stage, run_params=None: captured.update(
            sid=s, stage=stage, run_params=run_params
        ),
    )
    view = SessionView(root, app, sid)
    root.update_idletasks()
    try:
        view.count_spin_var.set(4)
        view._start_transcription()
        assert captured["stage"] == "transcribe"
        assert captured["run_params"] == {"expected_count": 4}
    finally:
        view.destroy()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/gui/test_transcribe_count_handoff.py -v`
Expected: FAIL — current `_start_transcription` calls `open_session_stage(sid, "transcribe")` with no `run_params`, so `captured["run_params"]` is `None`.

- [ ] **Step 3: Implement.**

(a) `app/ui/session_view.py` `_start_transcription` (current lines 390-393):

```python
    def _start_transcription(self) -> None:
        if self.app and hasattr(self.app, "open_session_stage"):
            self.app.open_session_stage(
                self.session_id, "transcribe", run_params=self._run_params_for_transcribe()
            )
```

(b) `app/ui/app_window.py` `open_session_stage` (current line 399) — add the param and forward it:

```python
    def open_session_stage(self, session_id: int, stage: str, run_params: dict | None = None):
        from app.data import db

        session = db.get_session(session_id)
        tab = {
            "transcribe": self.transcribe_tab,
            "summarize": self.summarize_tab,
            "refine": self.refine_tab,
        }.get(stage, self.transcribe_tab)
        if session is not None and hasattr(tab, "load_for_session"):
            tab.load_for_session(session, run_params=run_params)
        self.notebook.select(tab)
```

(c) `app/ui/transcribe_tab.py`:
- In `__init__` (near line 43 where `self.session_id` is set), add: `self._run_params: dict = {}`.
- `load_for_session` (current line 182) — accept and store run-params BEFORE calling `load_session`:

```python
    def load_for_session(self, session: dict, run_params: dict | None = None) -> None:
        """Set the active session and derive speakers.json from its campaign_slug
        (current library version), falling back to the session's stored path."""
        self.session_id = int(session["id"])
        self.active_slug = session.get("campaign_slug")
        self.speakers_path = self._resolve_speakers_path(session)
        self.load_session(self.session_id)
        self._run_params = run_params or {}
```

- `load_session` (current line 200) — reset run-params so a manual reopen (session dropdown / History) doesn't reuse stale ① values. Add at the end of the method (after `self.session_id = sid`):

```python
        self._run_params = {}
```

  > Ordering: `load_for_session` calls `load_session` (which clears `_run_params`) and THEN sets `_run_params` from its argument — so the ① count survives a session-driven open, while a direct `load_session` leaves it empty (loose-file/exact behavior).

- `_worker` — replace the transcribe call (current lines 433-434):

```python
                from app.core import transcriber as _tr

                count_kwargs = _tr.diarization_run_kwargs(
                    (getattr(self, "_run_params", {}) or {}).get("expected_count"),
                    int(self.spk_var.get()),
                )
                segments = pipeline.transcribe_file(wav, progress=progress_cb, **count_kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/gui/test_transcribe_count_handoff.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/session_view.py app/ui/app_window.py app/ui/transcribe_tab.py tests/gui/test_transcribe_count_handoff.py
git commit -m "Wire ① expected-voice count (at-least-N window) into the transcribe run"
```

---

## Task 4: Full-suite verification

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all green (prior 194 + the new unit/GUI tests; 0 failures). Investigate any failure before proceeding.

- [ ] **Step 2: Lint + format**

Run: `.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format --check .`
Expected: clean.

- [ ] **Step 3: Grep for leftover exact-lock assumptions**

Run: `git grep -n "min_speakers\|max_speakers\|num_speakers\|_run_params" app/`
Expected: every diarization caller goes through `diarization_run_kwargs` / `speaker_count_window`; no stray `min=max=N` building outside `speaker_count_window`.

---

## Manual validation (USER, after the build)
1. Open a session with a roster → ① shows the editable **Expected voices for this run** spinbox, pre-seeded from the present roster.
2. Transcribe with the pre-seeded count → result is sensible; transcript + ② Review + Spec 2 voice pre-fill all still work.
3. On a session that previously **merged two people**, set the count to the true number (one higher) and re-transcribe → the missed voice appears as its own cluster in ② Review.
4. Loose-file (non-session) transcribe via the Transcribe tab spinbox → unchanged behavior.

---

## Self-review notes (against the spec)
- Spec "single expected-voice-count lever, per-session in ①, prominent/editable, pre-seeded" → Tasks 2/3. ✓
- Spec binding "at least N, room for one more (min=max(1,N), max=N+1)" → `diarization_run_kwargs` (Task 1). ✓
- Spec "supersedes default-5 for session runs; loose-file exact unchanged" → `_worker` uses run-params when present, else `num_speakers=spk_var` (exact). ✓
- Spec "no DB/schema/migration; in-memory handoff" → run-params threaded through `open_session_stage`/`load_for_session`. ✓
- Spec "transcript/embedding path unchanged" → only the `min/max_speakers` kwargs change; the single-pass call is untouched. ✓
- Spec "#51 deferred (threshold inert)" → no clustering-threshold code in this plan. ✓
