# Campaign Home & Session Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a campaign the owner of its sessions and replace the four scattered tabs (Campaigns / Discover / Build Profile / History) with a unified **Home** hub, a campaign-scoped **Edit Profile** screen, and a session-driven flow with two lightweight checkpoints (① Confirm who's here, ② Review speakers) — all with manual per-session voice assignment.

**Architecture:** The data layer links `sessions.campaign_slug` to a `library` campaign (nullable for loose/uncategorized sessions) and reuses the per-session `speaker_profiles` rows as the session-local voice→person override layer. The `library` engine (immutable versioned `speakers.json` docs) is reused as-is; only the **doc schema** is extended with per-speaker `ignore`/role state and a campaign-level `npcs` list. The UI collapses to `Home · Transcribe · Summarize · Refine · ⚙`: Home merges Campaigns+History, Edit Profile replaces Build Profile, and Transcribe/Summarize/Refine become session-driven (the `CampaignPicker` is retired).

**Tech Stack:** Python 3.11, Tkinter/ttk + app.ui.theme, app.core.library, app.data.db (SQLite), stdlib only.

**Repo:** Imagination-Industries-LLC/CampaignScribe. Branch: feature/campaign-home-redesign. Spec 1 of 2 (Spec 2 = voice-fingerprint auto-match, OUT OF SCOPE here).

---

## Pre-flight (do first, at execution time)
- [ ] **Confirm branch + baseline.** `git branch --show-current` must print `feature/campaign-home-redesign` (already cut off `main`, which includes the merged #22 Campaign Library — `git log --oneline -3` should show commit `42ebe51 Campaign Speakers Library … (#22)`).
- [ ] **Rebase if behind.** `git fetch origin && git rebase origin/main`. Resolve any conflicts preserving both #22 and this branch's design-spec commit.
- [ ] **Green baseline.** Run `.venv\Scripts\python -m pytest -q`. Confirm a fully green suite BEFORE starting. If the Windows lane shows `gui` tests, they run here; the Linux CI lane skips `gui` and runs only `tests/unit/`.
- [ ] **Read the spec.** `docs/superpowers/specs/2026-05-31-campaign-home-redesign.md` is the source of truth.

## Ground rules (bake into every task)
- Plain single-line commit messages. **NO** AI-attribution trailer (no `Co-Authored-By`, no "built with Claude Code"). Functional Anthropic Claude API references are fine.
- Never introduce the string "MeetingScribe" anywhere.
- `ruff check .` must be clean; full `pytest` green before each commit.
- Any subprocess call (none new expected) must pass `creationflags=subprocess.CREATE_NO_WINDOW`.
- Preserve GPU-preferred behavior (do not touch `transcriber.check_gpu` / device selection).
- Reuse `app/core/library.py` for versioning — do NOT reimplement storage.
- Tk-free logic → `tests/unit/` (runs on the Linux lane). GUI → mark `@pytest.mark.gui` with a `root`/`app` fixture that `pytest.skip`s on `tk.TclError` (Windows lane).

## File Structure (created / modified)
| File | Responsibility |
| --- | --- |
| `app/data/db.py` *(modify)* | Add `campaign_slug TEXT` column + migration `_m2`; extend `create_session`/`update_session`/`list_sessions` for the slug. |
| `app/core/speakers_io.py` *(modify)* | Extend doc schema: per-speaker `ignore` flag round-trip + campaign-level `npcs: [{name, notes}]`; keep backward-compat defaults. |
| `app/core/summarizer.py` *(modify)* | Thread `known_npcs: list[str] \| None = None` into `summarize_part`/`consolidate_summaries`; when present, append a `Known NPCs in this campaign: …` line to the prompt. Back-compat: default None → unchanged prompt. |
| `app/ui/home_tab.py` *(create)* | `HomeTab` — the hub: campaign list + search + Uncategorized + New/Import (left); roster summary + Edit profile + session list + New session + reopen/rename/delete (right). |
| `app/ui/edit_profile_window.py` *(create)* | `EditProfileWindow` — a `tk.Toplevel` (mirrors `SessionView`): campaign-scoped roster editor: voice→person rows, grouped Ignored voices + promote, NPC tags, Context, Versions panel, Import/Export/Save-as-new-version, Discover-from-audio. Opened from Home + the campaign roster strip; breadcrumb = window title + Close/Back. NOT a notebook tab. |
| `app/ui/session_view.py` *(create)* | `SessionView` Toplevel — header + audio + pipeline stepper; ① Confirm who's here, ② Review speakers (manual assignment → session-local mapping, populated from the detected clusters persisted by the Transcribe stage; Save-to-profile promotes a version). |
| `app/ui/transcribe_tab.py` *(modify)* | Drop `CampaignPicker`/`_on_picker_change`; add `load_for_session(session)` active-session context; inputs come from the session. **Persist the detected voice clusters** (per-session `speaker_profiles` rows + `num_speakers_detected`) onto the session after a run, so checkpoint ② reads real clusters. |
| `app/ui/summarize_tab.py` *(modify)* | Same: drop picker; `load_for_session(session)`. |
| `app/ui/refine_tab.py` *(modify)* | Same: drop picker; `load_for_session(session)`; "accept" appends a version via the session's `campaign_slug`. |
| `app/ui/app_window.py` *(modify)* | New `_tab_specs` = Home · Transcribe · Summarize · Refine (+ ⚙); remove old tabs; renumber labels + `Ctrl+1..4`; widget-based nav. `open_edit_profile(slug)` opens an `EditProfileWindow` Toplevel (NOT a 5th tab). |
| `app/ui/campaign_picker.py` *(delete)* | Retired. |
| `app/ui/campaigns_tab.py`, `app/ui/history_tab.py`, `app/ui/discover_tab.py`, `app/ui/build_profile_tab.py` *(delete)* | Folded into Home / Edit Profile / session flow. |
| `tests/unit/test_db_campaign_slug.py` *(create)* | Tk-free DB migration + slug-filter tests. |
| `tests/unit/test_speakers_doc_schema.py` *(create)* | Tk-free doc-schema round-trip tests. |
| `tests/unit/test_summarizer_npcs.py` *(create)* | Tk-free: `known_npcs` names appear in the prompt sent to the faked Claude client; None/empty → unchanged (back-compat). |
| `tests/unit/test_consuming_pickers.py`, `tests/unit/test_campaign_picker.py` *(delete)* | Picker retired. |
| `tests/gui/test_home_tab.py`, `tests/gui/test_edit_profile_window.py`, `tests/gui/test_session_view.py`, `tests/gui/test_stage_tabs_session.py` *(create)* | GUI tests for the new screens. |
| `tests/smoke/test_app_smoke.py` *(modify)* | New EXPECTED_LABELS + 4-tab assertions. |
| `tests/smoke/test_campaign_home.py` *(create)* | End-to-end smoke: create campaign → new session → run a stage on the active session. |

---

### Task 1: DB — add `campaign_slug` column + migration (Tk-free)

**Files:** Modify `app/data/db.py`; Create `tests/unit/test_db_campaign_slug.py`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_db_campaign_slug.py`):

```python
"""sessions.campaign_slug: migration, create/update, and slug filtering."""

from __future__ import annotations

import sqlite3

from app.config import get_db_path
from app.data import db


def test_fresh_db_has_campaign_slug_column():
    db.init_db()
    with sqlite3.connect(str(get_db_path())) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(sessions)")}
    assert "campaign_slug" in cols


def test_create_session_with_slug_persists():
    db.init_db()
    sid = db.create_session("S1", campaign_name="Strahd", campaign_slug="strahd")
    s = db.get_session(sid)
    assert s["campaign_slug"] == "strahd"


def test_create_session_defaults_slug_to_null():
    db.init_db()
    sid = db.create_session("Loose")
    assert db.get_session(sid)["campaign_slug"] is None


def test_update_session_sets_slug():
    db.init_db()
    sid = db.create_session("S1")
    db.update_session(sid, campaign_slug="strahd")
    assert db.get_session(sid)["campaign_slug"] == "strahd"


def test_list_sessions_filters_by_slug():
    db.init_db()
    a = db.create_session("A", campaign_slug="strahd")
    db.create_session("B", campaign_slug="wildemount")
    loose = db.create_session("C")
    got = {s["id"] for s in db.list_sessions(campaign_slug="strahd")}
    assert got == {a}
    loose_ids = {s["id"] for s in db.list_sessions(campaign_slug=db.UNCATEGORIZED)}
    assert loose in loose_ids
    assert a not in loose_ids


def test_list_sessions_no_filter_returns_all():
    db.init_db()
    db.create_session("A", campaign_slug="strahd")
    db.create_session("B")
    assert len(db.list_sessions()) == 2


def test_migration_preserves_existing_rows_and_adds_null_slug(tmp_path, monkeypatch):
    # Simulate a pre-migration (v1) DB: baseline schema WITHOUT campaign_slug.
    dbp = get_db_path()
    dbp.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(dbp)) as c:
        c.execute(
            "CREATE TABLE sessions ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " display_name TEXT NOT NULL DEFAULT 'Untitled Session',"
            " campaign_name TEXT, status TEXT DEFAULT 'new')"
        )
        c.execute("INSERT INTO sessions(display_name, campaign_name) VALUES ('Old', 'Strahd')")
        c.execute("PRAGMA user_version = 1")
        c.commit()
    db.init_db()  # must run _m2 in place, not drop the row
    rows = db.list_sessions()
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Old"
    assert rows[0]["campaign_slug"] is None
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/unit/test_db_campaign_slug.py -q` → fails on missing `campaign_slug`, `UNCATEGORIZED`, and the keyword args.

- [ ] **Step 3: Implement.** In `app/data/db.py`:
  - Add `campaign_slug TEXT` to the `CREATE TABLE … sessions` block in `SCHEMA_SQL` (after `campaign_name TEXT,`):
    ```python
        campaign_name TEXT,
        campaign_slug TEXT,
    ```
  - Add a sentinel + bump the baseline-vs-migration path. Above `SCHEMA_BASELINE`:
    ```python
    # list_sessions(campaign_slug=UNCATEGORIZED) lists loose/null-slug sessions.
    UNCATEGORIZED = "\x00__uncategorized__"
    ```
  - Add the migration so existing v1 databases gain the column in place:
    ```python
    def _m2(conn: sqlite3.Connection) -> None:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "campaign_slug" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN campaign_slug TEXT")


    _MIGRATIONS: list = [(2, _m2)]
    ```
    (Replace the existing empty `_MIGRATIONS: list = []`.)
  - Add `"campaign_slug"` to the `_SESSION_COLUMNS` allowlist set.
  - Extend `create_session`:
    ```python
    def create_session(
        display_name: str,
        campaign_name: str = "",
        source_audio_files: list[str] | None = None,
        campaign_slug: str | None = None,
    ) -> int:
        with get_conn() as c:
            cur = c.execute(
                "INSERT INTO sessions(display_name, campaign_name, source_audio_files, "
                "campaign_slug) VALUES (?, ?, ?, ?)",
                (
                    display_name or "Untitled Session",
                    campaign_name or "",
                    json.dumps(source_audio_files or []),
                    campaign_slug,
                ),
            )
            return int(cur.lastrowid)
    ```
  - Extend `list_sessions` with the slug filter (keep the existing `search` behavior):
    ```python
    def list_sessions(search: str = "", campaign_slug: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if search:
            clauses.append("(display_name LIKE ? OR campaign_name LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        if campaign_slug == UNCATEGORIZED:
            clauses.append("campaign_slug IS NULL")
        elif campaign_slug is not None:
            clauses.append("campaign_slug = ?")
            params.append(campaign_slug)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with get_conn() as c:
            rows = c.execute(
                f"SELECT * FROM sessions{where} ORDER BY created_at DESC",  # nosec B608 - static clause fragments; values parameterized
                params,
            ).fetchall()
        return [dict(r) for r in rows]
    ```
  - `update_session(campaign_slug=…)` already works via the `**fields` allowlist now that the column is added.

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/unit/test_db_campaign_slug.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/data/db.py tests/unit/test_db_campaign_slug.py` then
  `git add -A && git commit -m "DB: link sessions to campaigns via nullable campaign_slug"`

---

### Task 2: speakers_io — extend doc schema (ignore state + NPCs) (Tk-free)

**Files:** Modify `app/core/speakers_io.py`; Create `tests/unit/test_speakers_doc_schema.py`.

The existing doc has `players[]` and `known_non_players[]`. Spec extends with (a) a per-speaker boolean `ignore` flag on roster entries (remembered so re-processing keeps them ignored) and (b) a campaign-level `npcs: [{name, notes}]` list for summary context. Backward-compat: docs lacking these fields must still load.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_speakers_doc_schema.py`):

```python
"""Doc-schema extension: per-speaker ignore flag + campaign-level npcs list."""

from __future__ import annotations

import json

from app.core import library, speakers_io


def test_empty_doc_has_npcs_and_ignore_defaults():
    doc = speakers_io.empty_speakers_doc("Strahd")
    assert doc["npcs"] == []
    assert doc["players"] == []


def test_profiles_to_doc_marks_ignored_speaker():
    speakers = [
        {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
        {"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0},
    ]
    doc = speakers_io.profiles_to_speakers_doc("Strahd", "", speakers, npcs=[])
    assert any(n.get("ignore") is True for n in doc["known_non_players"])
    assert all(p["player_name"] != "TV" for p in doc["players"])


def test_profiles_to_doc_round_trips_npcs():
    npcs = [{"name": "Strahd", "notes": "the vampire"}]
    doc = speakers_io.profiles_to_speakers_doc("Strahd", "ctx", [], npcs=npcs)
    assert doc["npcs"] == npcs


def test_old_doc_without_npcs_still_loads(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"campaign": "Old", "players": []}), encoding="utf-8")
    doc = speakers_io.load_speakers_json(str(p))
    assert doc["npcs"] == []  # default-filled
    assert doc["campaign"] == "Old"


def test_npcs_and_ignore_round_trip_through_library(tmp_path):
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd",
        "",
        [{"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0}],
        npcs=[{"name": "Strahd", "notes": "vampire"}],
    )
    library.add_version(slug, doc)
    got = library.get_current_doc(slug)
    assert got["npcs"] == [{"name": "Strahd", "notes": "vampire"}]
    assert any(n.get("ignore") is True for n in got["known_non_players"])
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/unit/test_speakers_doc_schema.py -q`

- [ ] **Step 3: Implement.** In `app/core/speakers_io.py`:
  - `empty_speakers_doc` — add `"npcs": []`:
    ```python
    def empty_speakers_doc(campaign: str = "", context: str = "") -> dict[str, Any]:
        return {
            "campaign": campaign,
            "context": context,
            "known_non_players": [],
            "npcs": [],
            "fallback_policy": dict(DEFAULT_FALLBACK_POLICY),
            "players": [],
        }
    ```
  - `load_speakers_json` — add the back-compat default after the existing `setdefault` calls:
    ```python
        data.setdefault("npcs", [])
    ```
  - `profiles_to_speakers_doc` — add an `npcs` parameter and stamp the explicit `ignore` flag on non-player entries:
    ```python
    def profiles_to_speakers_doc(
        campaign: str,
        context: str,
        speakers: list[dict[str, Any]],
        npcs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Transform UI-edited profiles into the speakers.json schema."""
        doc = empty_speakers_doc(campaign=campaign, context=context)
        doc["npcs"] = list(npcs or [])
        for sp in speakers:
            included = bool(sp.get("include_in_tracking", 1))
            role = (sp.get("role") or "").strip()
            entry = {
                "player_name": sp.get("display_name", "") or sp.get("source_speaker_id", ""),
                "role": role or "Player",
                "character_name": sp.get("character_name", ""),
                "character_class": sp.get("character_class", ""),
                "notes": sp.get("notes", ""),
                "speech_patterns": sp.get("speech_patterns") or [],
                "source_speaker_id": sp.get("source_speaker_id", ""),
            }
            if not included or role == "Non-Player":
                non_player = {
                    "name": entry["player_name"],
                    "role": "ignore" if not included else (role or "Non-Player"),
                    "ignore": not included,
                    "notes": entry["notes"],
                    "speech_patterns": entry["speech_patterns"],
                    "source_speaker_id": entry["source_speaker_id"],
                }
                doc["known_non_players"].append(non_player)
            else:
                doc["players"].append(entry)
        return doc
    ```

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/unit/test_speakers_doc_schema.py tests/unit/test_library.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/core/speakers_io.py tests/unit/test_speakers_doc_schema.py` then
  `git add -A && git commit -m "speakers_io: add per-speaker ignore flag and campaign npcs list"`

---

### Task 3: Summarizer — feed campaign NPCs into the summary prompt (Tk-free)

**Files:** Modify `app/core/summarizer.py`; Create `tests/unit/test_summarizer_npcs.py`.

Spec decision 4: NPCs are "fed to the summarizer" so recaps read "the party met Strahd." Add a `known_npcs: list[str] | None = None` parameter to `summarize_part` and `consolidate_summaries`. When present and non-empty, append a `Known NPCs in this campaign: …` line to the prompt that goes to Claude. Default `None`/empty → prompt is byte-for-byte unchanged (back-compat). The Summarize call site (rewired in Task 7) pulls the NPC names from the active session's campaign profile and passes them in.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_summarizer_npcs.py`). The `fake_claude` fixture (see `tests/conftest.py`) returns a `FakeClient` whose `.calls` is a list of the kwargs passed to `messages.create(...)`; the prompt is `calls[0]["messages"][0]["content"]`:

```python
"""known_npcs threads campaign NPCs into the summary prompt sent to Claude."""

from __future__ import annotations

from app.core import summarizer


def _prompt_of(client) -> str:
    assert client.calls, "messages.create was never called"
    return client.calls[0]["messages"][0]["content"]


def test_summarize_part_includes_known_npcs(fake_claude):
    client = fake_claude(["a part summary"])
    summarizer.summarize_part(
        "TRANSCRIPT TEXT",
        {"campaign": "Strahd", "context": "", "players": []},
        "Summarize this session.",
        "sk-test",
        part_number=1,
        known_npcs=["Strahd", "Ireena"],
    )
    prompt = _prompt_of(client)
    assert "Known NPCs in this campaign:" in prompt
    assert "Strahd" in prompt
    assert "Ireena" in prompt


def test_summarize_part_without_npcs_is_unchanged(fake_claude):
    client_a = fake_claude(["s"])
    summarizer.summarize_part(
        "T", {"campaign": "C", "context": "", "players": []}, "P", "sk", part_number=1
    )
    base_prompt = _prompt_of(client_a)
    assert "Known NPCs in this campaign:" not in base_prompt

    client_b = fake_claude(["s"])
    summarizer.summarize_part(
        "T", {"campaign": "C", "context": "", "players": []}, "P", "sk",
        part_number=1, known_npcs=[],
    )
    assert _prompt_of(client_b) == base_prompt  # empty list == None == unchanged


def test_consolidate_includes_known_npcs(fake_claude):
    client = fake_claude(["SESSION NAME: X\n\nbody"])
    summarizer.consolidate_summaries(
        ["part 1 summary"],
        {"campaign": "Strahd", "context": ""},
        "sk-test",
        known_npcs=["Strahd"],
    )
    assert "Strahd" in _prompt_of(client)
    assert "Known NPCs in this campaign:" in _prompt_of(client)
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/unit/test_summarizer_npcs.py -q` → fails on the unexpected `known_npcs` keyword.

- [ ] **Step 3: Implement.** In `app/core/summarizer.py`:
  - Add a tiny helper above `summarize_part`:
    ```python
    def _npc_line(known_npcs: list[str] | None) -> str:
        """A trailing prompt line naming the campaign's NPCs, or '' when none."""
        names = [n for n in (known_npcs or []) if n]
        if not names:
            return ""
        return "Known NPCs in this campaign: " + ", ".join(names) + "\n"
    ```
  - Extend `summarize_part`'s signature and append the line to `full_prompt`:
    ```python
    def summarize_part(
        transcript_text: str,
        speakers_reference: dict[str, Any],
        summary_prompt: str,
        api_key: str,
        part_number: int = 1,
        known_npcs: list[str] | None = None,
    ) -> str:
        """Run a single transcript part through Claude with the user's chosen prompt."""
        client = _client(api_key)
        campaign_context_block = json.dumps(
            {
                "campaign": speakers_reference.get("campaign", ""),
                "context": speakers_reference.get("context", ""),
                "players": speakers_reference.get("players", []),
            },
            indent=2,
            ensure_ascii=False,
        )

        full_prompt = (
            f"{summary_prompt}\n\n"
            f"========================================================\n"
            f"CAMPAIGN CONTEXT (from speakers.json):\n"
            f"========================================================\n"
            f"{campaign_context_block}\n"
            f"{_npc_line(known_npcs)}\n"
            f"========================================================\n"
            f"TRANSCRIPT — PART {part_number}\n"
            f"========================================================\n"
            f"{transcript_text}\n"
        )
        ...
    ```
    (Keep the existing `client.messages.create(...)` / `return` body unchanged. Note: `_npc_line` returns `""` when `known_npcs` is None/empty, so `full_prompt` is identical to today's prompt — the back-compat test relies on this exact equality, so do NOT change surrounding `\n` spacing.)
  - Extend `consolidate_summaries` the same way: add `known_npcs: list[str] | None = None` to the signature, then inject the line into `prompt` right after the `CAMPAIGN CONTEXT:` block:
    ```python
    def consolidate_summaries(
        part_summaries: list[str],
        speakers_reference: dict[str, Any],
        api_key: str,
        known_npcs: list[str] | None = None,
    ) -> dict[str, str]:
        ...
        prompt = (
            "You are consolidating individual part summaries from a D&D session into one "
            "unified session summary.\n\n"
            f"CAMPAIGN CONTEXT:\n{context_block}\n"
            f"{_npc_line(known_npcs)}\n"
            f"INDIVIDUAL PART SUMMARIES:\n{parts_block}\n\n"
            ...
        )
    ```
    (Adjust only the join so the with-NPCs branch adds the line and the without-NPCs branch is unchanged: the original had `f"CAMPAIGN CONTEXT:\n{context_block}\n\n"` — splitting it into `…{context_block}\n"` + `f"{_npc_line(known_npcs)}\n"` keeps the empty-NPC output identical.)

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/unit/test_summarizer_npcs.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/core/summarizer.py tests/unit/test_summarizer_npcs.py` then
  `git add -A && git commit -m "Summarizer: feed campaign NPC names into the summary prompt"`

> The Summarize *call site* that supplies `known_npcs` from the active session's campaign profile is wired in Task 7 (Summarize stage rewiring), where the session→slug→`library.get_current_doc(slug)["npcs"]` lookup already exists.

---

### Task 4: Home tab — `HomeTab` merging Campaigns + History

**Files:** Create `app/ui/home_tab.py`; Create `tests/gui/test_home_tab.py`.

`HomeTab` is the hub. Left: search, campaign list, an "Uncategorized" row, New campaign, Import. Right (selected campaign): one-line roster summary + "Edit profile ▸", session list (state chips), "＋ New session", reopen/rename/delete. It calls into `library` and `db` directly and opens `EditProfileWindow` / `SessionView` Toplevels via the app (wired in later tasks; for this task the buttons call `self.app.open_edit_profile(slug)` / `self.app.open_session(session_id)`, which the GUI test stubs).

- [ ] **Step 1: Write the failing tests** (`tests/gui/test_home_tab.py`):

```python
"""HomeTab: campaign list + Uncategorized, session list, new campaign/session."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library
from app.data import db

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
    calls = {"edit": [], "session": []}
    app = types.SimpleNamespace(
        notebook=None,
        open_edit_profile=lambda slug: calls["edit"].append(slug),
        open_session=lambda sid: calls["session"].append(sid),
    )
    app._calls = calls
    return app


def test_home_lists_campaigns_and_uncategorized(root):
    db.init_db()
    library.create_campaign("Strahd")
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, _app())
    root.update_idletasks()
    labels = [home.campaign_list.get(i) for i in range(home.campaign_list.size())]
    assert any("Strahd" in s for s in labels)
    assert any("Uncategorized" in s for s in labels)


def test_selecting_campaign_lists_its_sessions(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    db.create_session("Night 1", campaign_name="Strahd", campaign_slug=slug)
    db.create_session("Loose")
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, _app())
    root.update_idletasks()
    home.select_campaign(slug)
    root.update_idletasks()
    names = [home.session_tree.set(i, "name") for i in home.session_tree.get_children()]
    assert "Night 1" in names
    assert "Loose" not in names


def test_uncategorized_lists_loose_sessions(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    db.create_session("Night 1", campaign_slug=slug)
    db.create_session("Loose")
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, _app())
    root.update_idletasks()
    home.select_uncategorized()
    root.update_idletasks()
    names = [home.session_tree.set(i, "name") for i in home.session_tree.get_children()]
    assert names == ["Loose"]


def test_new_session_creates_linked_record_and_opens(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    app = _app()
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, app)
    root.update_idletasks()
    home.select_campaign(slug)
    sid = home._new_session()  # returns the new session id
    assert sid is not None
    assert db.get_session(sid)["campaign_slug"] == slug
    assert app._calls["session"] == [sid]


def test_edit_profile_button_invokes_app(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    app = _app()
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, app)
    root.update_idletasks()
    home.select_campaign(slug)
    home._edit_profile()
    assert app._calls["edit"] == [slug]


def test_delete_session_record_removes_row(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.home_tab import HomeTab

    home = HomeTab(root, _app())
    root.update_idletasks()
    home.select_campaign(slug)
    home.selected_session_id = sid
    home._delete_session(confirm=False)
    assert db.get_session(sid) is None
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/gui/test_home_tab.py -q`

- [ ] **Step 3: Implement** `app/ui/home_tab.py`:

```python
"""Home: the campaign + session hub. Merges Campaigns and History."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from app import config
from app.core import library
from app.data import db
from app.ui.theme import BTN_ACCENT, BTN_DANGER, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3

STATUS_CHIP = {
    "new": "🆕 recorded",
    "onboarded": "🔄 onboarded",
    "transcribed": "📝 transcribed",
    "summarized": "✅ summarized",
}

UNCATEGORIZED_LABEL = "▣ Uncategorized (loose sessions)"


class HomeTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self._rows: list[str | None] = []  # parallel to campaign_list; None = Uncategorized
        self.selected_slug: str | None = None
        self.selected_is_uncat = False
        self.selected_session_id: int | None = None

        pad = {"padx": S_3, "pady": S_2}
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Campaign Home", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad
        )

        # ---- Left: campaigns ----
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsw", **pad)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_campaigns())
        ttk.Entry(left, textvariable=self.search_var, width=28).pack(fill="x")
        ttk.Label(left, text="Campaign", style=LBL_DIM).pack(anchor="w", pady=(S_2, 0))
        self.campaign_list = tk.Listbox(left, width=30, height=18, exportselection=False)
        self.campaign_list.pack(fill="both", expand=True)
        self.campaign_list.bind("<<ListboxSelect>>", self._on_campaign_select)
        ttk.Button(left, text="＋ New campaign…", style=BTN_GHOST, command=self._new_campaign).pack(
            fill="x", pady=(S_2, 0)
        )
        ttk.Button(
            left, text="Import existing .json…", style=BTN_GHOST, command=self._import
        ).pack(fill="x", pady=(S_2, 0))

        # ---- Right: detail ----
        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew", **pad)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self.title_var = tk.StringVar(value="Select a campaign")
        ttk.Label(right, textvariable=self.title_var, style=LBL_HEADER).grid(
            row=0, column=0, sticky="w"
        )
        roster_row = ttk.Frame(right)
        roster_row.grid(row=1, column=0, sticky="ew", pady=(0, S_2))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(roster_row, textvariable=self.summary_var, style=LBL_DIM).pack(side="left")
        self.edit_btn = ttk.Button(
            roster_row, text="Edit profile ▸", style=BTN_GHOST, command=self._edit_profile
        )
        self.edit_btn.pack(side="right")

        ttk.Button(
            right, text="＋ New session", style=BTN_ACCENT, command=self._new_session
        ).grid(row=2, column=0, sticky="w", pady=(0, S_2))

        cols = ("id", "name", "created", "status")
        self.session_tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        for c, head, w in (
            ("id", "ID", 50),
            ("name", "Session", 280),
            ("created", "Created", 140),
            ("status", "Status", 150),
        ):
            self.session_tree.heading(c, text=head)
            self.session_tree.column(c, width=w, anchor="w")
        self.session_tree.grid(row=3, column=0, sticky="nsew")
        self.session_tree.bind("<<TreeviewSelect>>", self._on_session_select)
        self.session_tree.bind("<Double-Button-1>", lambda _e: self._open_selected_session())

        actions = ttk.Frame(right)
        actions.grid(row=4, column=0, sticky="w", pady=(S_2, 0))
        ttk.Button(actions, text="Open", style=BTN_GHOST, command=self._open_selected_session).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Rename…", style=BTN_GHOST, command=self._rename_session).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(
            actions, text="Delete record…", style=BTN_DANGER, command=self._delete_session
        ).pack(side="left")

        self._refresh_campaigns()

    # ---------- lifecycle ----------
    def on_settings_changed(self):
        pass

    def on_show(self):
        self._refresh_campaigns()

    # ---------- campaigns ----------
    def _refresh_campaigns(self):
        query = self.search_var.get().strip().lower()
        rows = library.list_campaigns()
        self._rows = []
        self.campaign_list.delete(0, "end")
        for r in rows:
            if query and query not in r["display_name"].lower():
                continue
            self._rows.append(r["slug"])
            self.campaign_list.insert("end", f"{r['display_name']}  ({r['version_count']}v)")
        self._rows.append(None)  # Uncategorized bucket always last
        self.campaign_list.insert("end", UNCATEGORIZED_LABEL)
        if self.selected_is_uncat:
            self.select_uncategorized()
        elif self.selected_slug in self._rows:
            self.select_campaign(self.selected_slug)
        else:
            self._clear_detail()

    def _on_campaign_select(self, _e=None):
        sel = self.campaign_list.curselection()
        if not sel:
            return
        target = self._rows[sel[0]]
        if target is None:
            self.select_uncategorized()
        else:
            self.select_campaign(target)

    def select_campaign(self, slug: str):
        self.selected_slug = slug
        self.selected_is_uncat = False
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        if row is None:
            self._clear_detail()
            return
        self.title_var.set(row["display_name"])
        try:
            doc = library.get_current_doc(slug)
            players = doc.get("players", [])
            dms = sum(1 for p in players if "dungeon master" in (p.get("role", "").lower()))
            self.summary_var.set(
                f"v{row['version_count']} · {len(players)} players · {dms} DM · "
                f"{len(doc.get('npcs', []))} NPCs"
            )
        except Exception:
            self.summary_var.set(f"v{row['version_count']} · no profile yet")
        self.edit_btn.state(["!disabled"])
        self._refresh_sessions(db.list_sessions(campaign_slug=slug))

    def select_uncategorized(self):
        self.selected_slug = None
        self.selected_is_uncat = True
        self.title_var.set("Uncategorized")
        self.summary_var.set("Loose sessions not filed into a campaign")
        self.edit_btn.state(["disabled"])
        self._refresh_sessions(db.list_sessions(campaign_slug=db.UNCATEGORIZED))

    def _clear_detail(self):
        self.selected_slug = None
        self.selected_is_uncat = False
        self.title_var.set("Select a campaign")
        self.summary_var.set("")
        self.session_tree.delete(*self.session_tree.get_children())

    # ---------- sessions ----------
    def _refresh_sessions(self, sessions):
        self.session_tree.delete(*self.session_tree.get_children())
        for s in sessions:
            self.session_tree.insert(
                "",
                "end",
                iid=str(s["id"]),
                values=(
                    s["id"],
                    s["display_name"],
                    (s.get("created_at") or "")[:16],
                    STATUS_CHIP.get(s.get("status", "new"), s.get("status", "?")),
                ),
            )

    def _on_session_select(self, _e=None):
        sel = self.session_tree.selection()
        self.selected_session_id = int(sel[0]) if sel else None

    def _new_session(self):
        if self.selected_is_uncat:
            slug = None
            name = "Untitled Campaign"
        elif self.selected_slug:
            slug = self.selected_slug
            row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
            name = row["display_name"] if row else ""
        else:
            messagebox.showinfo("CampaignScribe", "Select a campaign first.")
            return None
        sid = db.create_session("Untitled Session", campaign_name=name, campaign_slug=slug)
        self._refresh_sessions(
            db.list_sessions(
                campaign_slug=db.UNCATEGORIZED if slug is None else slug
            )
        )
        self.app.open_session(sid)
        return sid

    def _open_selected_session(self):
        if self.selected_session_id is None:
            messagebox.showinfo("CampaignScribe", "Select a session first.")
            return
        self.app.open_session(self.selected_session_id)

    def _rename_session(self):
        if self.selected_session_id is None:
            return
        new = simpledialog.askstring("Rename session", "New name:", parent=self)
        if not new or not new.strip():
            return
        db.update_session(self.selected_session_id, display_name=new.strip())
        self._reload_current()

    def _delete_session(self, confirm: bool = True):
        if self.selected_session_id is None:
            return
        if confirm and not messagebox.askyesno(
            "Delete session record",
            "Remove this session record from the database?\n\nFiles on disk are NOT deleted.",
        ):
            return
        db.delete_session(self.selected_session_id)
        self.selected_session_id = None
        self._reload_current()

    def _reload_current(self):
        if self.selected_is_uncat:
            self.select_uncategorized()
        elif self.selected_slug:
            self.select_campaign(self.selected_slug)

    # ---------- campaign actions ----------
    def _edit_profile(self):
        if not self.selected_slug:
            messagebox.showinfo("CampaignScribe", "Select a campaign first.")
            return
        self.app.open_edit_profile(self.selected_slug)

    def _new_campaign(self):
        name = simpledialog.askstring("New campaign", "Campaign name:", parent=self)
        if not name or not name.strip():
            return
        self.selected_slug = library.create_campaign(name.strip())
        self.selected_is_uncat = False
        self._refresh_campaigns()

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.selected_slug = library.import_file(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Import failed:\n{e}")
            return
        config.set_last_dir("json", path)
        self.selected_is_uncat = False
        self._refresh_campaigns()
```

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/gui/test_home_tab.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/ui/home_tab.py tests/gui/test_home_tab.py` then
  `git add -A && git commit -m "Home tab: campaign + session hub merging Campaigns and History"`

---

### Task 5: Edit Profile — `EditProfileWindow` campaign-scoped roster editor (Toplevel)

**Files:** Create `app/ui/edit_profile_window.py`; Create `tests/gui/test_edit_profile_window.py`.

Replaces Build Profile. Implemented as a **`tk.Toplevel`** (mirrors `SessionView` in Task 6), NOT a notebook tab — opened by `app.open_edit_profile(slug)` from Home and the campaign roster strip. The breadcrumb is the window title plus a "◂ Home" Close/Back button that destroys the window. Loaded by slug (`load_campaign(slug)`), never session-first. Reuses the `SpeakerEditor` block pattern from the old `build_profile_tab.py`. Adds: a grouped "Ignored voices" section with "↑ Track as player" promote, an NPC tag list (name + notes), a Context box, a Versions panel (reuse `library.list_versions`/`set_current`), Import/Export/Save-as-new-version, and "⟲ Discover from audio…" reusing `speaker_id.discover_speakers` + the diarization pipeline (the exact worker logic from the old `discover_tab._worker`, minus the DB session-creation — it just appends discovered voices to the editor list).

- [ ] **Step 1: Write the failing tests** (`tests/gui/test_edit_profile_window.py`). Mirror the `SessionView` tests' construction/teardown: a `root` Tk fixture that skips on `tk.TclError`, and construct `EditProfileWindow(root, app_stub, slug)` (the Toplevel loads the campaign in its constructor). The app stub provides what `SessionView`'s stub provides (`notebook=None`, `open_home`):

```python
"""EditProfileWindow: load a campaign, edit roster, ignore/promote, NPCs, save version."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library, speakers_io
from app.data import db

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
    return types.SimpleNamespace(notebook=None, open_home=lambda: None)


def _seeded_campaign():
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd",
        "gothic horror",
        [
            {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
            {"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0},
        ],
        npcs=[{"name": "Strahd", "notes": "the vampire"}],
    )
    library.add_version(slug, doc)
    return slug


def test_load_campaign_splits_players_and_ignored(root):
    db.init_db()
    slug = _seeded_campaign()
    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        assert len(win.editors) == 1  # Mike, a tracked player
        assert len(win.ignored) == 1  # TV, ignored
        assert win.context_box.get("1.0", "end").strip() == "gothic horror"
    finally:
        win.destroy()


def test_npcs_loaded_into_list(root):
    db.init_db()
    slug = _seeded_campaign()
    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        assert [n["name"] for n in win.npcs] == ["Strahd"]
    finally:
        win.destroy()


def test_save_as_new_version_appends(root):
    db.init_db()
    slug = _seeded_campaign()
    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        before = len(library.list_versions(slug))
        win._save_new_version()
        assert len(library.list_versions(slug)) == before + 1
    finally:
        win.destroy()


def test_promote_ignored_to_player(root):
    db.init_db()
    slug = _seeded_campaign()
    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        win._promote_ignored(0)  # promote TV
        root.update_idletasks()
        assert len(win.editors) == 2
        assert len(win.ignored) == 0
        win._save_new_version()
        doc = library.get_current_doc(slug)
        assert any(p["player_name"] == "TV" for p in doc["players"])
    finally:
        win.destroy()


def test_add_npc(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, speakers_io.empty_speakers_doc("Strahd"))
    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        win._add_npc_direct("Ireena", "Strahd's obsession")
        win._save_new_version()
        assert library.get_current_doc(slug)["npcs"] == [
            {"name": "Ireena", "notes": "Strahd's obsession"}
        ]
    finally:
        win.destroy()
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/gui/test_edit_profile_window.py -q`

- [ ] **Step 3: Implement** `app/ui/edit_profile_window.py`. Copy the `SpeakerEditor` class verbatim from the old `build_profile_tab.py` (it stays a good per-speaker form), then implement `EditProfileWindow` as a `tk.Toplevel` (mirror `SessionView`'s container + open/close mechanics: `super().__init__(master)`, set a window title, `withdraw`/`grab`/`deiconify` like `SessionView`, and a Close/Back button that `self.destroy()`s):

```python
"""Edit Profile: campaign-scoped, versioned roster editor Toplevel. Replaces Build Profile."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from app import config
from app.core import library, speakers_io
from app.ui.common import ScrollableFrame
from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3

ROLE_OPTIONS = ["Dungeon Master", "Player", "Non-Player", "Unknown"]


class SpeakerEditor(ttk.LabelFrame):
    # <copy the full SpeakerEditor class body from the old build_profile_tab.py
    #  unchanged: __init__ building the row, and collect() returning the dict>
    ...


class EditProfileWindow(tk.Toplevel):
    def __init__(self, master, app_window, slug: str):
        super().__init__(master)
        self.app = app_window
        self.slug: str | None = None
        self.editors: list[SpeakerEditor] = []
        self.ignored: list[dict[str, Any]] = []  # ignored voices (raw dicts)
        self.npcs: list[dict[str, Any]] = []
        self._busy = False
        self._cancel = threading.Event()

        self.title("Edit Profile")
        self.geometry("760x680")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        pad = {"padx": S_3, "pady": S_2}

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Button(bar, text="◂ Home", style=BTN_GHOST, command=self._back_home).pack(side="left")
        self.title_var = tk.StringVar(value="Edit Profile")
        ttk.Label(bar, textvariable=self.title_var, style=LBL_HEADER).pack(side="left", padx=S_3)
        ttk.Button(bar, text="Save as new version", style=BTN_ACCENT, command=self._save_new_version).pack(
            side="right"
        )
        ttk.Button(bar, text="Export copy…", style=BTN_GHOST, command=self._export).pack(
            side="right", padx=S_2
        )
        ttk.Button(bar, text="Import…", style=BTN_GHOST, command=self._import).pack(side="right")

        ctx_row = ttk.Frame(self)
        ctx_row.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(ctx_row, text="Context (campaign tone, setting):", style=LBL_DIM).pack(anchor="w")
        self.context_box = tk.Text(ctx_row, height=2, wrap="word")
        self.context_box.pack(fill="x")

        tools = ttk.Frame(self)
        tools.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Button(tools, text="＋ Add player", style=BTN_GHOST, command=self._add_player).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(
            tools, text="⟲ Discover from audio…", style=BTN_GHOST, command=self._discover_from_audio
        ).pack(side="left", padx=(0, S_2))
        ttk.Button(tools, text="＋ NPC…", style=BTN_GHOST, command=self._add_npc).pack(side="left")
        self.npc_var = tk.StringVar()
        ttk.Label(tools, textvariable=self.npc_var, style=LBL_DIM).pack(side="left", padx=S_3)

        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=3, column=0, sticky="nsew", **pad)

        ver_row = ttk.LabelFrame(self, text="Versions")
        ver_row.grid(row=4, column=0, sticky="ew", **pad)
        self.versions = ttk.Treeview(
            ver_row, columns=("v", "created", "label"), show="headings", height=4
        )
        for c, w in (("v", 60), ("created", 160), ("label", 200)):
            self.versions.heading(c, text=c.title())
            self.versions.column(c, width=w, anchor="w")
        self.versions.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        vbtns = ttk.Frame(ver_row)
        vbtns.pack(side="left", padx=4)
        ttk.Button(vbtns, text="View", style=BTN_GHOST, command=self._view_version).pack(fill="x", pady=2)
        ttk.Button(vbtns, text="Set current", style=BTN_GHOST, command=self._set_current).pack(fill="x", pady=2)

        # Load the campaign into the editor (mirrors SessionView ending its
        # __init__ with its render calls). Close/Back is the "◂ Home" button,
        # which destroys this Toplevel.
        self.load_campaign(slug)

    # ---------- load ----------
    def load_campaign(self, slug: str) -> None:
        self.slug = slug
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        self.title_var.set(f"Edit Profile — {row['display_name'] if row else slug}")
        try:
            doc = library.get_current_doc(slug)
        except FileNotFoundError:
            doc = speakers_io.empty_speakers_doc(row["display_name"] if row else "")
        self.npcs = list(doc.get("npcs", []))
        self.context_box.delete("1.0", "end")
        self.context_box.insert("1.0", doc.get("context", "") or "")
        players = [
            {
                "source_speaker_id": p.get("source_speaker_id", ""),
                "display_name": p.get("player_name", ""),
                "character_name": p.get("character_name", ""),
                "character_class": p.get("character_class", ""),
                "role": p.get("role", "Player"),
                "include_in_tracking": 1,
                "notes": p.get("notes", ""),
                "speech_patterns": p.get("speech_patterns", []),
                "sample_quotes": [],
                "confidence": "high",
            }
            for p in doc.get("players", [])
        ]
        self.ignored = [
            {
                "source_speaker_id": n.get("source_speaker_id", ""),
                "display_name": n.get("name", ""),
                "notes": n.get("notes", ""),
                "speech_patterns": n.get("speech_patterns", []),
            }
            for n in doc.get("known_non_players", [])
        ]
        self._render(players)
        self._refresh_npc_label()
        self._refresh_versions()

    def _render(self, players):
        for w in list(self.scroll.inner.winfo_children()):
            w.destroy()
        self.editors.clear()
        ttk.Label(self.scroll.inner, text="Players & DM", style=LBL_HEADER).pack(anchor="w", pady=(4, 2))
        for sp in players:
            ed = SpeakerEditor(self.scroll.inner, sp)
            ed.pack(fill="x", padx=4, pady=4)
            self.editors.append(ed)
        # Ignored voices group
        ttk.Label(self.scroll.inner, text="Ignored voices", style=LBL_DIM).pack(anchor="w", pady=(10, 2))
        for i, n in enumerate(self.ignored):
            row = ttk.Frame(self.scroll.inner)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=f"⌀ {n['display_name'] or '(unnamed)'}   IGNORED", style=LBL_DIM).pack(
                side="left"
            )
            ttk.Button(
                row, text="↑ Track as player", style=BTN_GHOST,
                command=lambda idx=i: self._promote_ignored(idx),
            ).pack(side="right")

    def _add_player(self):
        sp = {"source_speaker_id": "", "display_name": "", "role": "Player", "include_in_tracking": 1}
        ed = SpeakerEditor(self.scroll.inner, sp)
        ed.pack(fill="x", padx=4, pady=4)
        self.editors.append(ed)

    def _promote_ignored(self, idx: int):
        n = self.ignored.pop(idx)
        players = [ed.collect() for ed in self.editors]
        players.append(
            {
                "source_speaker_id": n.get("source_speaker_id", ""),
                "display_name": n.get("display_name", ""),
                "character_name": "",
                "character_class": "",
                "role": "Player",
                "include_in_tracking": 1,
                "notes": n.get("notes", ""),
                "speech_patterns": n.get("speech_patterns", []),
                "sample_quotes": [],
                "confidence": "high",
            }
        )
        self._render(players)

    # ---------- NPCs ----------
    def _add_npc(self):
        name = simpledialog.askstring("Add NPC", "NPC name:", parent=self)
        if not name or not name.strip():
            return
        notes = simpledialog.askstring("Add NPC", "Notes (optional):", parent=self) or ""
        self._add_npc_direct(name.strip(), notes.strip())

    def _add_npc_direct(self, name: str, notes: str):
        self.npcs.append({"name": name, "notes": notes})
        self._refresh_npc_label()

    def _refresh_npc_label(self):
        self.npc_var.set(
            "NPCs: " + (", ".join(n["name"] for n in self.npcs) if self.npcs else "(none)")
        )

    # ---------- versions ----------
    def _refresh_versions(self):
        self.versions.delete(*self.versions.get_children())
        if not self.slug:
            return
        versions = library.list_versions(self.slug)
        cur = next((r["current"] for r in library.list_campaigns() if r["slug"] == self.slug), "")
        total = len(versions)
        for i, v in enumerate(reversed(versions)):
            num = total - i
            mark = "  ← current" if v["file"] == cur else ""
            self.versions.insert(
                "", "end", iid=v["file"], values=(f"v{num}{mark}", v["created_at"], v.get("label") or "")
            )

    def _view_version(self):
        sel = self.versions.selection()
        if not sel or not self.slug:
            return
        from app.ui.common import open_path_native

        open_path_native(str(library.version_path(self.slug, sel[0])))

    def _set_current(self):
        sel = self.versions.selection()
        if not sel or not self.slug:
            return
        library.set_current(self.slug, sel[0])
        self.load_campaign(self.slug)

    # ---------- save / import / export ----------
    def _build_doc(self) -> dict[str, Any]:
        speakers = [ed.collect() for ed in self.editors]
        speakers += [
            {"display_name": n["display_name"], "role": "Non-Player", "include_in_tracking": 0,
             "notes": n.get("notes", ""), "speech_patterns": n.get("speech_patterns", []),
             "source_speaker_id": n.get("source_speaker_id", "")}
            for n in self.ignored
        ]
        row = next((r for r in library.list_campaigns() if r["slug"] == self.slug), None)
        return speakers_io.profiles_to_speakers_doc(
            campaign=row["display_name"] if row else "",
            context=self.context_box.get("1.0", "end").strip(),
            speakers=speakers,
            npcs=self.npcs,
        )

    def _save_new_version(self):
        if not self.slug:
            return
        library.add_version(self.slug, self._build_doc())
        self._refresh_versions()
        messagebox.showinfo("CampaignScribe", "Saved a new profile version.")

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path or not self.slug:
            return
        try:
            doc = speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        config.set_last_dir("json", path)
        library.add_version(self.slug, doc, label="imported")
        self.load_campaign(self.slug)

    def _export(self):
        if not self.slug:
            return
        dest = filedialog.asksaveasfilename(
            title="Export copy…", defaultextension=".json", initialfile="speakers.json",
            initialdir=config.get_last_dir("json") or None, filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        speakers_io.save_speakers_json(dest, self._build_doc())
        config.set_last_dir("json", dest)
        messagebox.showinfo("CampaignScribe", f"Exported to {dest}")

    def _back_home(self):
        self.destroy()
        if hasattr(self.app, "open_home"):
            self.app.open_home()

    # ---------- discover from audio ----------
    def _discover_from_audio(self):
        # Reuses the diarization + Claude profiling worker from the retired
        # discover_tab: convert -> TranscriptionPipeline.transcribe_file ->
        # speaker_id.discover_speakers, then APPEND the returned profiles to the
        # editor list (no DB session is created here — this only seeds the roster).
        from app.core import audio, speaker_id, transcriber

        path = filedialog.askopenfilename(
            title="Discover speakers from audio",
            initialdir=config.get_last_dir("audio") or None,
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm")],
        )
        if not path:
            return
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        if not api_key or not hf:
            messagebox.showerror(
                "CampaignScribe", "Discover needs an Anthropic API key and a HuggingFace token (Settings ⚙)."
            )
            return
        config.set_last_dir("audio", path)
        self.npc_var.set("Discovering speakers from audio…")

        def worker():
            wav = None
            try:
                wav = audio.convert_to_wav(path)
                pipeline = transcriber.TranscriptionPipeline(
                    model_size=config.load_config().get("default_whisper_model", "small"), hf_token=hf
                )
                segments = pipeline.transcribe_file(wav, num_speakers=int(
                    config.load_config().get("default_num_speakers", 5)
                ))
                result = speaker_id.discover_speakers(segments, api_key)
                pipeline.close()
            except Exception as e:  # noqa: BLE001 - surfaced to the user below
                config.log_exception("edit_profile.discover", e)
                self.after(0, lambda: messagebox.showerror("CampaignScribe", str(e)))
                return
            finally:
                import os

                if wav and os.path.exists(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass

            def apply():
                for prof in result.get("profiles", []):
                    sp = {
                        "source_speaker_id": prof.get("source_speaker_id", ""),
                        "display_name": prof.get("suggested_display_name", ""),
                        "role": "Dungeon Master"
                        if prof.get("inferred_role", "").upper() == "DM"
                        else (prof.get("inferred_role") or "Player"),
                        "include_in_tracking": 1,
                        "notes": prof.get("notes", ""),
                        "speech_patterns": prof.get("speech_patterns", []),
                        "sample_quotes": prof.get("sample_quotes", []),
                        "confidence": prof.get("confidence", "medium"),
                    }
                    ed = SpeakerEditor(self.scroll.inner, sp)
                    ed.pack(fill="x", padx=4, pady=4)
                    self.editors.append(ed)
                self._refresh_npc_label()

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()
```

  Note: `_back_home` destroys the Toplevel and then calls `app.open_home()` (the app method is wired in Task 8); the GUI test stubs the app namespace (`open_home`) and tears the window down in a `finally` block.

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/gui/test_edit_profile_window.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/ui/edit_profile_window.py tests/gui/test_edit_profile_window.py` then
  `git add -A && git commit -m "Edit Profile: campaign-scoped roster editor with ignored voices and NPCs"`

---

### Task 6: Session detail + flow — `SessionView`

**Files:** Create `app/ui/session_view.py`; Create `tests/gui/test_session_view.py`.

`SessionView` is a `tk.Toplevel` opened by `app.open_session(session_id)`. It shows a header (breadcrumb + editable name + status pill), an audio list (`＋ add track`), a pipeline stepper, and the two checkpoints:
- **① Confirm who's here** — seed the expected roster from the campaign's current profile (its tracked players), let the user toggle "absent tonight" and add a guest. The confirmed count is `expected_speaker_count`.
- **② Review speakers** — for each detected cluster, a dropdown to assign a roster member / guest / ignore; writes the session-local mapping via per-session `speaker_profiles` (`db.add_speaker_profile`). "Save changes to profile ▸" promotes the mapping to a new campaign version via `library.add_version`.

The expensive transcription pass itself is run by the Transcribe stage (Task 7) on the active session; `SessionView` provides the ①/② scaffolding and a "Start transcription ▸" button that calls `app.open_session_stage(session_id, "transcribe")`.

- [ ] **Step 1: Write the failing tests** (`tests/gui/test_session_view.py`):

```python
"""SessionView: ① expected count from roster, ② manual assignment + promote."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library, speakers_io
from app.data import db

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


def _campaign_with_two_players():
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd",
        "",
        [
            {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
            {"display_name": "Jo", "role": "Player", "include_in_tracking": 1},
        ],
        npcs=[],
    )
    library.add_version(slug, doc)
    return slug


def _app():
    return types.SimpleNamespace(
        notebook=None, open_session_stage=lambda sid, stage: None, open_home=lambda: None
    )


def test_confirm_seeds_expected_count_from_roster(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    assert view.expected_speaker_count() == 2  # Mike + Jo, none marked absent


def test_marking_absent_reduces_expected_count(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.mark_absent("Jo")
    assert view.expected_speaker_count() == 1


def test_add_guest_increases_expected_count(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.add_guest("Visitor")
    assert view.expected_speaker_count() == 3


def test_review_assignment_writes_session_local_mapping(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.assign_cluster("SPEAKER_00", "Mike")
    view.assign_cluster("SPEAKER_01", "__ignore__")
    view._save_session_mapping()
    rows = db.get_speakers_for_session(sid)
    by_src = {r["source_speaker_id"]: r for r in rows}
    assert by_src["SPEAKER_00"]["display_name"] == "Mike"
    assert by_src["SPEAKER_01"]["include_in_tracking"] == 0


def test_save_to_profile_adds_version(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.assign_cluster("SPEAKER_00", "Mike")
    before = len(library.list_versions(slug))
    view._save_to_profile()
    assert len(library.list_versions(slug)) == before + 1


def test_loose_session_has_no_roster_but_constructs(root):
    db.init_db()
    sid = db.create_session("One-shot")  # null slug
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    assert view.expected_speaker_count() == 0
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/gui/test_session_view.py -q`

- [ ] **Step 3: Implement** `app/ui/session_view.py`:

```python
"""Session detail Toplevel: header, audio, pipeline stepper, ① confirm, ② review."""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core import library, speakers_io
from app.data import db
from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3

IGNORE_CHOICE = "__ignore__"
GUEST_CHOICE = "__guest__"


class SessionView(tk.Toplevel):
    def __init__(self, master, app_window, session_id: int):
        super().__init__(master)
        self.app = app_window
        self.session_id = session_id
        self.session = db.get_session(session_id) or {}
        self.slug = self.session.get("campaign_slug")
        self._roster: list[str] = []        # tracked player names from the profile
        self._absent: set[str] = set()       # names marked absent tonight
        self._guests: list[str] = []         # extra expected guests
        self._assignments: dict[str, str] = {}  # cluster id -> roster name / guest / __ignore__

        self.title(f"Session — {self.session.get('display_name', 'Untitled')}")
        self.geometry("760x640")
        pad = {"padx": S_3, "pady": S_2}

        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="◂ Home", style=BTN_GHOST, command=self._back_home).pack(side="left")
        self.name_var = tk.StringVar(value=self.session.get("display_name", ""))
        ttk.Entry(bar, textvariable=self.name_var, width=40).pack(side="left", padx=S_3)
        ttk.Button(bar, text="Rename", style=BTN_GHOST, command=self._rename).pack(side="left")
        self.status_var = tk.StringVar(value=self.session.get("status", "new"))
        ttk.Label(bar, textvariable=self.status_var, style=LBL_DIM).pack(side="right")

        # Audio
        audio_lf = ttk.LabelFrame(self, text="Audio")
        audio_lf.pack(fill="x", **pad)
        self.audio_box = tk.Listbox(audio_lf, height=3)
        self.audio_box.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        ttk.Button(audio_lf, text="＋ add track", style=BTN_GHOST, command=self._add_track).pack(
            side="left", padx=4
        )
        for f in json.loads(self.session.get("source_audio_files") or "[]"):
            self.audio_box.insert("end", f)

        # ① Confirm who's here
        confirm_lf = ttk.LabelFrame(self, text="① Confirm who's here")
        confirm_lf.pack(fill="x", **pad)
        self.confirm_inner = ttk.Frame(confirm_lf)
        self.confirm_inner.pack(fill="x", padx=4, pady=4)
        self.count_var = tk.StringVar()
        ttk.Label(confirm_lf, textvariable=self.count_var, style=LBL_DIM).pack(anchor="w", padx=4)
        crow = ttk.Frame(confirm_lf)
        crow.pack(fill="x", padx=4, pady=4)
        ttk.Button(crow, text="＋ add guest", style=BTN_GHOST, command=self._add_guest_dialog).pack(
            side="left"
        )
        ttk.Button(
            crow, text="Start transcription ▸", style=BTN_ACCENT, command=self._start_transcription
        ).pack(side="right")

        # ② Review speakers
        review_lf = ttk.LabelFrame(self, text="② Review speakers")
        review_lf.pack(fill="both", expand=True, **pad)
        self.review_inner = ttk.Frame(review_lf)
        self.review_inner.pack(fill="both", expand=True, padx=4, pady=4)
        rrow = ttk.Frame(review_lf)
        rrow.pack(fill="x", padx=4, pady=4)
        ttk.Button(
            rrow, text="Save changes to profile ▸", style=BTN_GHOST, command=self._save_to_profile
        ).pack(side="right")

        self._load_roster()
        self._render_confirm()
        self._render_review()

    # ---------- roster / ① ----------
    def _load_roster(self):
        self._roster = []
        if not self.slug:
            return
        try:
            doc = library.get_current_doc(self.slug)
        except Exception:
            return
        self._roster = [p.get("player_name", "") for p in doc.get("players", []) if p.get("player_name")]

    def _render_confirm(self):
        for w in list(self.confirm_inner.winfo_children()):
            w.destroy()
        self._absent_vars = {}
        for name in self._roster + self._guests:
            var = tk.BooleanVar(value=name not in self._absent)
            self._absent_vars[name] = var
            ttk.Checkbutton(
                self.confirm_inner, text=name, variable=var,
                command=lambda n=name: self._toggle_present(n),
            ).pack(anchor="w")
        self._update_count()

    def _toggle_present(self, name: str):
        if self._absent_vars[name].get():
            self._absent.discard(name)
        else:
            self._absent.add(name)
        self._update_count()

    def mark_absent(self, name: str):
        self._absent.add(name)
        self._render_confirm()

    def add_guest(self, name: str):
        self._guests.append(name)
        self._render_confirm()
        self._render_review()

    def _add_guest_dialog(self):
        from tkinter import simpledialog

        name = simpledialog.askstring("Add guest", "Guest name:", parent=self)
        if name and name.strip():
            self.add_guest(name.strip())

    def _update_count(self):
        self.count_var.set(f"Expected voices: {self.expected_speaker_count()}")

    def expected_speaker_count(self) -> int:
        present = [n for n in (self._roster + self._guests) if n not in self._absent]
        return len(present)

    # ---------- ② review ----------
    def _detected_clusters(self) -> list[str]:
        rows = db.get_speakers_for_session(self.session_id)
        if rows:
            return [r["source_speaker_id"] for r in rows if r.get("source_speaker_id")]
        n = self.session.get("num_speakers_detected") or 0
        return [f"SPEAKER_{i:02d}" for i in range(int(n))]

    def _render_review(self):
        for w in list(self.review_inner.winfo_children()):
            w.destroy()
        choices = [c for c in (self._roster + self._guests) if c not in self._absent]
        options = choices + [GUEST_CHOICE, IGNORE_CHOICE]
        self._review_vars = {}
        for cid in self._detected_clusters():
            row = ttk.Frame(self.review_inner)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=cid, width=16).pack(side="left")
            var = tk.StringVar(value=self._assignments.get(cid, ""))
            self._review_vars[cid] = var
            ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=30).pack(
                side="left"
            )

    def assign_cluster(self, cluster_id: str, target: str):
        self._assignments[cluster_id] = target
        if hasattr(self, "_review_vars") and cluster_id in self._review_vars:
            self._review_vars[cluster_id].set(target)

    def _collect_assignments(self) -> dict[str, str]:
        out = dict(self._assignments)
        for cid, var in getattr(self, "_review_vars", {}).items():
            if var.get():
                out[cid] = var.get()
        return out

    def _save_session_mapping(self):
        db.delete_speakers_for_session(self.session_id)
        for cid, target in self._collect_assignments().items():
            ignore = target == IGNORE_CHOICE
            name = "" if target in (IGNORE_CHOICE, GUEST_CHOICE) else target
            db.add_speaker_profile(
                self.session_id,
                {
                    "source_speaker_id": cid,
                    "display_name": name,
                    "role": "Non-Player" if ignore else "Player",
                    "include_in_tracking": 0 if ignore else 1,
                },
            )

    def _save_to_profile(self):
        self._save_session_mapping()
        if not self.slug:
            messagebox.showinfo("CampaignScribe", "This loose session has no campaign to update.")
            return
        rows = db.get_speakers_for_session(self.session_id)
        try:
            doc = library.get_current_doc(self.slug)
            npcs = doc.get("npcs", [])
            context = doc.get("context", "")
            campaign = doc.get("campaign", "")
        except Exception:
            npcs, context, campaign = [], "", ""
        speakers = [
            {
                "source_speaker_id": r["source_speaker_id"],
                "display_name": r["display_name"],
                "role": r.get("role", "Player"),
                "include_in_tracking": r.get("include_in_tracking", 1),
                "notes": r.get("notes", ""),
            }
            for r in rows
            if r.get("display_name") or not r.get("include_in_tracking", 1)
        ]
        new_doc = speakers_io.profiles_to_speakers_doc(campaign, context, speakers, npcs=npcs)
        library.add_version(self.slug, new_doc, label="from session")
        messagebox.showinfo("CampaignScribe", "Saved changes to the campaign profile.")

    # ---------- misc ----------
    def _add_track(self):
        paths = filedialog.askopenfilenames(
            title="Add audio track(s)",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm")],
        )
        if not paths:
            return
        existing = json.loads(self.session.get("source_audio_files") or "[]")
        for p in paths:
            if p not in existing:
                existing.append(p)
                self.audio_box.insert("end", p)
        db.update_session(self.session_id, source_audio_files=json.dumps(existing))
        self.session["source_audio_files"] = json.dumps(existing)

    def _rename(self):
        new = self.name_var.get().strip()
        if new:
            db.update_session(self.session_id, display_name=new)
            self.title(f"Session — {new}")

    def _start_transcription(self):
        self._save_session_mapping()
        if hasattr(self.app, "open_session_stage"):
            self.app.open_session_stage(self.session_id, "transcribe")

    def _back_home(self):
        self.destroy()
        if hasattr(self.app, "open_home"):
            self.app.open_home()
```

  Note: `db.add_speaker_profile` defaults `source_speaker_id` to `""` and the column comparison in `get_speakers_for_session` orders by it — the assignment path passes explicit ids so this is fine.

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/gui/test_session_view.py -q`

- [ ] **Step 5: ruff + commit.** `ruff check app/ui/session_view.py tests/gui/test_session_view.py` then
  `git add -A && git commit -m "Session view: confirm-who's-here and manual review-speakers flow"`

---

### Task 7: Stage rewiring — Transcribe / Summarize / Refine become session-driven

**Files:** Modify `app/ui/transcribe_tab.py`, `app/ui/summarize_tab.py`, `app/ui/refine_tab.py`; Delete `app/ui/campaign_picker.py`, `tests/unit/test_consuming_pickers.py`, `tests/unit/test_campaign_picker.py`; Create `tests/gui/test_stage_tabs_session.py`.

Each stage drops the `CampaignPicker` row + `_on_picker_change` and gains `load_for_session(session)` which sets the active session and derives `speakers_path` from the session's `campaign_slug` (its current library version) — falling back to the session's stored `speakers_json_path` for loose sessions.

- [ ] **Step 1: Write the failing tests** (`tests/gui/test_stage_tabs_session.py`):

```python
"""Stage tabs operate on the active session — no CampaignPicker."""

from __future__ import annotations

import importlib
import tkinter as tk
import types

import pytest

from app.core import library, speakers_io
from app.data import db

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


@pytest.mark.parametrize(
    "modpath,clsname",
    [
        ("app.ui.transcribe_tab", "TranscribeTab"),
        ("app.ui.summarize_tab", "SummarizeTab"),
        ("app.ui.refine_tab", "RefineTab"),
    ],
)
def test_stage_has_no_picker_and_loads_session(root, modpath, clsname):
    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, speakers_io.empty_speakers_doc("Strahd"))
    sid = db.create_session("Night 1", campaign_slug=slug)
    mod = importlib.import_module(modpath)
    tab = getattr(mod, clsname)(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    assert not hasattr(tab, "picker")
    tab.load_for_session(db.get_session(sid))
    assert tab.session_id == sid
    assert tab.speakers_path == str(library.current_version_path(slug))


def test_loose_session_falls_back_to_stored_speakers_path(root, tmp_path):
    db.init_db()
    f = tmp_path / "loose.json"
    speakers_io.save_speakers_json(str(f), speakers_io.empty_speakers_doc("Loose"))
    sid = db.create_session("One-shot")  # null slug
    db.update_session(sid, speakers_json_path=str(f))
    from app.ui.transcribe_tab import TranscribeTab

    tab = TranscribeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.load_for_session(db.get_session(sid))
    assert tab.speakers_path == str(f)


def test_campaign_picker_module_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.ui.campaign_picker")
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/gui/test_stage_tabs_session.py -q`

- [ ] **Step 3: Implement.** Apply the same shape to all three stage tabs. Concretely, for `transcribe_tab.py` (mirror in `summarize_tab.py` and `refine_tab.py`):
  - Remove `from app.ui.campaign_picker import CampaignPicker`.
  - Remove the picker construction lines (`self.picker = CampaignPicker(...)` and `.grid(...)`) and shift subsequent grid rows up by one (or leave the row empty — simplest is to delete the two lines and renumber `row=` values below them down by 1; grid tolerates gaps, so deletion alone is acceptable).
  - Remove `_on_picker_change` and any `self.picker.refresh()` / `self.picker.selected_path()` / `self.picker.select_file()` / `self.picker.selected_slug()` calls. In `on_show`, replace the picker-refresh body with just `self.refresh_sessions()` (transcribe/summarize) — Refine's `on_show` drops the picker line and keeps the rest.
  - Add the active-session loader and a slug→path resolver near `load_session`:
    ```python
    def load_for_session(self, session: dict) -> None:
        """Set the active session and derive speakers.json from its campaign_slug
        (current library version), falling back to the session's stored path."""
        self.session_id = int(session["id"])
        self.speakers_path = self._resolve_speakers_path(session)
        # populate audio/transcript inputs from the session as load_session did
        self.load_session(self.session_id)

    def _resolve_speakers_path(self, session: dict) -> str | None:
        slug = session.get("campaign_slug")
        if slug:
            try:
                return str(library.current_version_path(slug))
            except FileNotFoundError:
                pass
        return session.get("speakers_json_path")
    ```
  - Update the bodies of the existing `load_session(sid)` methods to no longer call `self.picker.select_file(spk)`; instead set `self.speakers_path` directly from `_resolve_speakers_path(s)` (where `s = db.get_session(sid)`). Keep the audio/transcript-file population logic.
  - Ensure `library` is imported in each module (`from app.core import library` — transcribe/summarize currently import only `speakers_io`; refine already imports `library`).
  - In `transcribe_tab._send_to_refine`, replace the picker-based handoff (`self.picker.selected_slug()` / `refine_tab.picker.*`) with: set `refine_tab.speakers_path = self.speakers_path` and `refine_tab.speakers_doc = speakers_io.load_speakers_json(self.speakers_path)` guarded by try/except, then `refine_tab.suggestions = doc; refine_tab._render_suggestions()`.
  - In `refine_tab`'s "accept" path (around line 419), replace `slug = self.picker.selected_slug()` with `slug = self.active_slug` where `load_for_session` stores `self.active_slug = session.get("campaign_slug")`. If `slug` is set, `library.add_version(slug, doc, label="refined")`; else save in place to `self.speakers_path`.

- [ ] **Step 4: Delete the retired picker + its tests.**
  `git rm app/ui/campaign_picker.py tests/unit/test_consuming_pickers.py tests/unit/test_campaign_picker.py`
  (If `tests/unit/test_campaign_picker.py` does not exist, omit it from the command.)

- [ ] **Step 5: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/gui/test_stage_tabs_session.py -q`

- [ ] **Step 6: ruff + commit.** `ruff check app/ui/transcribe_tab.py app/ui/summarize_tab.py app/ui/refine_tab.py tests/gui/test_stage_tabs_session.py` then
  `git add -A && git commit -m "Stages: session-driven Transcribe/Summarize/Refine; retire CampaignPicker"`

---

### Task 8: app_window + nav — new four-tab IA

**Files:** Modify `app/ui/app_window.py`; Modify `tests/smoke/test_app_smoke.py`; Delete `app/ui/campaigns_tab.py`, `app/ui/history_tab.py`, `app/ui/discover_tab.py`, `app/ui/build_profile_tab.py`.

- [ ] **Step 1: Update the smoke test first** (`tests/smoke/test_app_smoke.py`):
  - Replace `EXPECTED_LABELS`:
    ```python
    EXPECTED_LABELS = [
        "1. Home",
        "2. Transcribe",
        "3. Summarize",
        "4. Refine",
    ]
    ```
  - Rename/replace `test_app_window_constructs_with_seven_tabs`:
    ```python
    def test_app_window_constructs_with_four_tabs(app):
        assert len(app.notebook.tabs()) == 4
        assert app.home_tab.winfo_exists()
    ```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/smoke/test_app_smoke.py -q`

- [ ] **Step 3: Implement** `app/ui/app_window.py`:
  - Imports: remove `BuildProfileTab`, `CampaignsTab`, `DiscoverTab`, `HistoryTab`; add
    ```python
    from app.ui.home_tab import HomeTab
    from app.ui.edit_profile_window import EditProfileWindow
    from app.ui.session_view import SessionView
    ```
  - Replace the tab construction block (Edit Profile is a Toplevel opened on demand, NOT constructed here):
    ```python
    self.home_tab = HomeTab(self.notebook, self)
    self.transcribe_tab = TranscribeTab(self.notebook, self)
    self.summarize_tab = SummarizeTab(self.notebook, self)
    self.refine_tab = RefineTab(self.notebook, self)
    ```
  - Replace `_tab_specs` (Edit Profile is reached from Home, NOT a top-level tab):
    ```python
    self._tab_specs = [
        (self.home_tab, "1. Home", "campaigns"),
        (self.transcribe_tab, "2. Transcribe", "transcribe"),
        (self.summarize_tab, "3. Summarize", "summarize"),
        (self.refine_tab, "4. Refine", "refine"),
    ]
    ```
  - Add navigation helpers used by Home / Edit Profile / SessionView:
    ```python
    def open_home(self):
        self.notebook.select(self.home_tab)
        if hasattr(self.home_tab, "on_show"):
            self.home_tab.on_show()

    def open_edit_profile(self, slug: str):
        EditProfileWindow(self, self, slug)

    def open_session(self, session_id: int):
        SessionView(self, self, session_id)

    def open_session_stage(self, session_id: int, stage: str):
        from app.data import db

        session = db.get_session(session_id)
        tab = {
            "transcribe": self.transcribe_tab,
            "summarize": self.summarize_tab,
            "refine": self.refine_tab,
        }.get(stage, self.transcribe_tab)
        if session is not None and hasattr(tab, "load_for_session"):
            tab.load_for_session(session)
        self.notebook.select(tab)
    ```
  - Fix the `open_settings` `for tab in (...)` loop: replace the removed tabs with `self.home_tab` (keep the three stage tabs). Edit Profile is a Toplevel created on demand, so it is NOT in this loop.
  - Fix `_bind_shortcuts`: change `for i in range(1, 8)` to `for i in range(1, len(self._tab_specs) + 1)` so `Ctrl+1..4` map correctly.
  - Fix `_menu_open_audio`: replace the `self.discover_tab` fallback with `self.transcribe_tab` and its `_add_files`.
  - Update `_maybe_offer_library_import`: replace `self.campaigns_tab.on_show()` with `self.home_tab.on_show()` (and the `hasattr(self, "campaigns_tab")` guard with `home_tab`).
  - Update `_show_getting_started` body text: replace "Discover → Build Profile → Transcribe → Summarize" with "Home → New session → Transcribe → Summarize" (no MeetingScribe, no AI attribution).

- [ ] **Step 4: Delete the folded-in tab modules.**
  `git rm app/ui/campaigns_tab.py app/ui/history_tab.py app/ui/discover_tab.py app/ui/build_profile_tab.py`

- [ ] **Step 5: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/smoke/test_app_smoke.py -q`

- [ ] **Step 6: Grep for stragglers.** `git grep -n -E "campaigns_tab|history_tab|discover_tab|build_profile_tab|CampaignPicker"` — must return nothing except this plan/spec docs. Fix any code references.

- [ ] **Step 7: ruff + commit.** `ruff check app/ui/app_window.py tests/smoke/test_app_smoke.py` then
  `git add -A && git commit -m "App window: four-tab IA (Home/Transcribe/Summarize/Refine), retire old tabs"`

---

### Task 9: First-run back-link migration + final smoke

**Files:** Modify `app/ui/app_window.py` (extend the one-time migration); Create `tests/smoke/test_campaign_home.py`.

Best-effort, non-destructive: on first run, link existing sessions whose `campaign_slug IS NULL` to a same-named library campaign (exact `campaign_name` match, case-insensitive). Guarded by a config flag so it runs once.

- [ ] **Step 1: Write the failing tests** (`tests/smoke/test_campaign_home.py`):

```python
"""End-to-end: back-link migration + create campaign → session → run a stage."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.core import library
from app.data import db

pytestmark = pytest.mark.gui


def test_backlink_links_named_sessions_to_campaigns():
    db.init_db()
    slug = library.create_campaign("Strahd")
    sid = db.create_session("Night 1", campaign_name="strahd")  # null slug, name match (case-insensitive)
    from app.ui import app_window

    app_window.backlink_sessions_to_campaigns()
    assert db.get_session(sid)["campaign_slug"] == slug


def test_backlink_leaves_unmatched_sessions_loose():
    db.init_db()
    sid = db.create_session("One-shot", campaign_name="No Such Campaign")
    from app.ui import app_window

    app_window.backlink_sessions_to_campaigns()
    assert db.get_session(sid)["campaign_slug"] is None


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None,
                 "error": "stub", "smi_gpu_name": None},
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


def test_new_session_runs_through_open_session_stage(app):
    slug = library.create_campaign("Strahd")
    from app.core import speakers_io

    library.add_version(slug, speakers_io.empty_speakers_doc("Strahd"))
    sid = db.create_session("Night 1", campaign_slug=slug)
    app.open_session_stage(sid, "transcribe")
    assert app.transcribe_tab.session_id == sid
    assert app.notebook.select() == str(app.transcribe_tab)
```

- [ ] **Step 2: Run — expect FAIL.** `.venv\Scripts\python -m pytest tests/smoke/test_campaign_home.py -q`

- [ ] **Step 3: Implement.** In `app/ui/app_window.py` add a module-level function:

```python
def backlink_sessions_to_campaigns() -> int:
    """Non-destructive: link null-slug sessions to a same-named library campaign
    (case-insensitive exact name match). Returns the count linked."""
    from app.core import library
    from app.data import db

    by_name = {c["display_name"].strip().lower(): c["slug"] for c in library.list_campaigns()}
    linked = 0
    for s in db.list_sessions(campaign_slug=db.UNCATEGORIZED):
        name = (s.get("campaign_name") or "").strip().lower()
        slug = by_name.get(name)
        if slug:
            db.update_session(s["id"], campaign_slug=slug)
            linked += 1
    return linked
```

  Then call it once from `_maybe_offer_library_import` (or a sibling one-time hook) guarded by a new config flag `sessions_backlinked`:
    ```python
    cfg = config.load_config()
    if not cfg.get("sessions_backlinked"):
        try:
            backlink_sessions_to_campaigns()
        except Exception:
            pass
        cfg = config.load_config()
        cfg["sessions_backlinked"] = True
        config.save_config(cfg)
    ```

- [ ] **Step 4: Run — expect PASS.** `.venv\Scripts\python -m pytest tests/smoke/test_campaign_home.py -q`

- [ ] **Step 5: Full suite + ruff.**
  `.venv\Scripts\python -m pytest -q` (all green) then `ruff check .` (clean).

- [ ] **Step 6: Commit.**
  `git add -A && git commit -m "First-run back-link of named sessions to campaigns; end-to-end smoke"`

---

## Self-Review (during planning)

### Spec-coverage checklist (each spec section → task)
- Locked decision 1 (campaign owns sessions) → Task 1 (`campaign_slug`) + Task 4 (Home lists a campaign's sessions).
- Locked decision 2 (loose/uncategorized allowed) → Task 1 (`UNCATEGORIZED` filter, null slug) + Task 4 (`select_uncategorized`).
- Locked decision 3 (session-local overrides + promote) → Task 6 (`_save_session_mapping`, `_save_to_profile`).
- Locked decision 4 (NPCs as summary context) → Task 2 (`npcs` in doc) + Task 3 (summarizer prompt wiring) + Task 5 (NPC list editor) + Task 7 (call site supplies `known_npcs`).
- Locked decision 5 (ignored voices remembered) → Task 2 (`ignore` flag) + Task 5 (Ignored voices group + promote).
- Locked decision 6 (Home = Layout A, merges Campaigns+History) → Task 4.
- Locked decision 7 (flow B+: ①/②) → Task 6.
- Locked decision 8 (manual assignment) → Task 6 (`assign_cluster` dropdowns; no auto-match).
- IA/nav (4 tabs; remove Discover/BuildProfile/Campaigns/History; stages session-driven; Edit Profile not a tab; retire picker) → Tasks 7, 8.
- Data model (`campaign_slug`; session-local `speaker_profiles`; doc `ignore`/`npcs`; versioning unchanged) → Tasks 1, 2, 6.
- Screens: Home → Task 4; Edit Profile (top bar, Context, Players & DM, Ignored, NPCs, Versions, Discover) → Task 5; Session detail (header, audio, stepper, ①, ②) → Task 6.
- Test plan (DB migration; doc round-trip; summarizer NPCs; Home gui; Edit Profile gui; session flow gui; stages session-driven; smoke order) → Tasks 1–9.
- Reused #22 (`library.py` unchanged engine) → respected; only doc schema extended (Task 2).

### Placeholder scan
No "TBD"/"similar to Task N"/"add error handling" placeholders in implementation steps. The only `...` is the explicit instruction to **copy the `SpeakerEditor` class verbatim** from the existing `build_profile_tab.py` (a deliberate, named reuse, not a stub) — the source is fully present in the repo at execution time.

### Type / name consistency
- `campaign_slug` (DB column + kwarg) consistent across `create_session`, `update_session`, `list_sessions`, Home, SessionView, stage tabs, back-link.
- `db.UNCATEGORIZED` sentinel used consistently for the loose-session filter.
- `npcs` shape `[{"name", "notes"}]` consistent in `empty_speakers_doc`, `profiles_to_speakers_doc(npcs=…)`, Edit Profile, SessionView.
- `HomeTab`, `EditProfileWindow`, `SessionView` class names match imports in `app_window.py`.
- `load_for_session(session: dict)` consistent across all three stage tabs and `open_session_stage`.
- `open_home` / `open_edit_profile` / `open_session` / `open_session_stage` consistent between `app_window.py` and the screens that call them.
- `EXPECTED_LABELS` = `["1. Home", "2. Transcribe", "3. Summarize", "4. Refine"]` consistent between Task 8 smoke and `_tab_specs`.

### Gaps surfaced for the requester

All brainstorm gaps are now resolved in-plan:
1. **NPC consumption by the summarizer — RESOLVED.** Task 3 threads a `known_npcs` parameter into `summarize_part`/`consolidate_summaries` and appends a `Known NPCs in this campaign: …` line to the prompt; Task 7's Summarize stage rewiring supplies the names from the active session's campaign profile (`library.get_current_doc(slug)["npcs"]`) at the call site.
2. **`num_speakers_detected` source for ② before a real run — RESOLVED.** Task 7's stage rewiring persists the detected voice clusters (per-session `speaker_profiles` rows + `num_speakers_detected`) onto the session after a Transcribe run, so `SessionView._detected_clusters` (Task 6's ②) reads real clusters instead of placeholders.
3. **Edit Profile as a 5th/transient notebook tab — RESOLVED.** Edit Profile is now a `tk.Toplevel` (`EditProfileWindow`, Task 5) opened by `app.open_edit_profile(slug)` (Task 8), mirroring `SessionView`. The notebook stays exactly 4 tabs (Home · Transcribe · Summarize · Refine), so the 4-tab smoke assertion holds with no transient-tab caveat.
