# Campaign Speakers Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-floating `speakers.json` files with a managed **library** organized by **campaign → auto-versioned history**: a first-position "Campaigns" tab to organize/preserve them, a Campaign picker that replaces the browse-for-file in the speaker tabs, explicit import, and export-anywhere preserved.

**Architecture:** A Tk-free engine (`app/core/library.py`) owns a folder tree under `%APPDATA%\CampaignScribe\library\<slug>\` (immutable timestamped version files + a per-campaign `manifest.json`). A reusable `CampaignPicker` widget resolves a selected campaign to its current-version **file path**, so the existing `speakers_io.load_speakers_json(path)` call sites are unchanged. A new `CampaignsTab` is the management home; Build Profile saves new versions; Refine's "accept" appends a new version.

**Tech Stack:** Python 3.11, Tkinter/ttk + `app.ui.theme`, the existing `app.core.speakers_io` (atomic writes), stdlib only.

**Repo:** `Imagination-Industries-LLC/CampaignScribe`. Phase 1, unit #15. Branch: `feature/campaigns-library`.

---

## Pre-flight (do first, at execution time)
- [ ] **Rebase onto current `main`.** This branch was cut before Theme PR #15 + org-rename PR #21 merged. Run `git fetch origin && git rebase origin/main`. Theme touched `app_window.py`/`config.py`/`settings_dialog.py`; resolve conflicts in favor of *both* changes. Re-run `pytest` (should be green) before starting.
- [ ] Confirm `git grep Imagination-Industries-Inc` is empty (org-rename merged).

## Ground rules
- Plain commits (no AI attribution); no predecessor-product name; ruff-clean; tests green; `CREATE_NO_WINDOW` on any subprocess (none added).
- **Tab-index churn:** inserting "Campaigns" first shifts every tab index. Update `_tab_specs`, the `Ctrl+1..N` loop, and any index-based logic; the smoke test asserts the new label order.

## Data model — `manifest.json` (per campaign)
```json
{
  "display_name": "Curse of Strahd",
  "created_at": "2026-05-30T14:12:33",
  "updated_at": "2026-05-31T09:02:10",
  "current": "2026-05-31T090210.json",
  "versions": [
    {"file": "2026-05-30T141233.json", "created_at": "2026-05-30T14:12:33", "label": null},
    {"file": "2026-05-31T090210.json", "created_at": "2026-05-31T09:02:10", "label": "after session 4"}
  ]
}
```
Version files are immutable `speakers.json` docs; `current` points at one of `versions[].file`.

---

### Task 1: Library engine — `app/core/library.py` (Tk-free) + unit tests

**Files:** Create `app/core/library.py`; Test `tests/unit/test_library.py`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_library.py`):

```python
"""Tests for app.core.library: campaigns, versions, manifest, import/export."""
from __future__ import annotations

import json

from app.core import library

DOC1 = {"campaign": "Curse of Strahd", "context": "gothic", "players": [{"player_name": "Mike"}],
        "known_non_players": [], "fallback_policy": {}}
DOC2 = {"campaign": "Curse of Strahd", "context": "gothic", "players": [{"player_name": "Mike"}, {"player_name": "Jo"}],
        "known_non_players": [], "fallback_policy": {}}


def test_create_and_list_campaign():
    slug = library.create_campaign("Curse of Strahd")
    assert slug == "curse-of-strahd"
    rows = library.list_campaigns()
    assert any(r["slug"] == slug and r["display_name"] == "Curse of Strahd" for r in rows)


def test_slugify_disambiguates_collisions():
    a = library.create_campaign("My Game!")
    b = library.create_campaign("my game")  # slugs to the same base
    assert a != b
    assert a == "my-game"
    assert b.startswith("my-game-")


def test_add_version_advances_current_and_grows_history():
    slug = library.create_campaign("Curse of Strahd")
    v1 = library.add_version(slug, DOC1)
    assert len(library.list_versions(slug)) == 1
    assert library.get_current_doc(slug)["players"] == DOC1["players"]
    v2 = library.add_version(slug, DOC2, label="s4")
    assert v2 != v1
    versions = library.list_versions(slug)
    assert len(versions) == 2
    assert library.get_current_doc(slug)["players"] == DOC2["players"]  # latest is current
    assert any(v["label"] == "s4" for v in versions)


def test_set_current_to_older_version():
    slug = library.create_campaign("C")
    v1 = library.add_version(slug, DOC1)
    library.add_version(slug, DOC2)
    library.set_current(slug, v1)
    assert library.get_current_doc(slug)["players"] == DOC1["players"]


def test_current_version_path_points_at_real_file():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    p = library.current_version_path(slug)
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_import_file_derives_campaign(tmp_path):
    f = tmp_path / "loose.json"
    f.write_text(json.dumps({"campaign": "Wildemount", "players": []}), encoding="utf-8")
    slug = library.import_file(str(f))
    assert slug == "wildemount"
    assert library.get_current_doc(slug)["campaign"] == "Wildemount"


def test_import_file_without_campaign_uses_filename(tmp_path):
    f = tmp_path / "MyParty.json"
    f.write_text(json.dumps({"players": []}), encoding="utf-8")
    slug = library.import_file(str(f))
    assert slug == "myparty"


def test_export_version_copies_bytes(tmp_path):
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    dest = tmp_path / "out" / "exported.json"
    library.export_version(slug, library.list_versions(slug)[0]["file"], str(dest))
    assert dest.exists()
    assert json.loads(dest.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_rename_campaign():
    slug = library.create_campaign("Old Name")
    library.add_version(slug, DOC1)
    new_slug = library.rename_campaign(slug, "New Name")
    assert new_slug == "new-name"
    assert library.get_current_doc(new_slug)["campaign"] == "Curse of Strahd"
    assert all(r["slug"] != slug for r in library.list_campaigns())


def test_delete_campaign():
    slug = library.create_campaign("Doomed")
    library.add_version(slug, DOC1)
    library.delete_campaign(slug)
    assert all(r["slug"] != slug for r in library.list_campaigns())


def test_manifest_recovery_when_corrupt():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    # corrupt the manifest
    (library._campaign_dir(slug) / "manifest.json").write_text("{ not json", encoding="utf-8")
    rows = library.list_campaigns()  # must not raise
    row = next(r for r in rows if r["slug"] == slug)
    assert row["version_count"] >= 1  # rebuilt from version files on disk


def test_add_version_atomic_no_temp_left():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    leftovers = list(library._campaign_dir(slug).glob("*.tmp"))
    assert leftovers == []
```
(Delete the `pytest.approx_any` placeholder line — it's illustrative; the explicit `len(...)==1` assertion below it is the real check. Remove that one line when writing the file.)

- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/unit/test_library.py -v` → FAIL (no module).

- [ ] **Step 3: Implement `app/core/library.py`:**

```python
"""Campaign speakers library: campaigns → auto-versioned speakers.json files.

Tk-free. Storage is a managed folder tree under %APPDATA%\\CampaignScribe\\library:
    <slug>/manifest.json + <timestamp>.json version files (immutable).
The manifest holds metadata + the current-version pointer; if it is missing or
corrupt it is rebuilt from the version files on disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_app_data_dir
from app.core import speakers_io


def library_root() -> Path:
    path = get_app_data_dir() / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "campaign"


def _campaign_dir(slug: str) -> Path:
    return library_root() / slug


def _unique_slug(display_name: str) -> str:
    base = _slugify(display_name)
    slug, n = base, 2
    while _campaign_dir(slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _manifest_path(slug: str) -> Path:
    return _campaign_dir(slug) / "manifest.json"


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _version_files(slug: str) -> list[str]:
    return sorted(p.name for p in _campaign_dir(slug).glob("*.json") if p.name != "manifest.json")


def _rebuild_manifest(slug: str) -> dict:
    files = _version_files(slug)
    versions = [{"file": f, "created_at": f[:-5], "label": None} for f in files]
    manifest = {
        "display_name": slug,
        "created_at": versions[0]["created_at"] if versions else "",
        "updated_at": versions[-1]["created_at"] if versions else "",
        "current": files[-1] if files else "",
        "versions": versions,
    }
    _atomic_write_json(_manifest_path(slug), manifest)
    return manifest


def _load_manifest(slug: str) -> dict:
    p = _manifest_path(slug)
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        if not isinstance(m, dict) or "versions" not in m:
            raise ValueError("bad manifest")
        return m
    except (OSError, ValueError):
        return _rebuild_manifest(slug)


def list_campaigns() -> list[dict]:
    out = []
    for d in sorted(library_root().iterdir()):
        if not d.is_dir():
            continue
        m = _load_manifest(d.name)
        out.append({
            "slug": d.name,
            "display_name": m.get("display_name") or d.name,
            "current": m.get("current", ""),
            "version_count": len(m.get("versions", [])),
            "updated_at": m.get("updated_at", ""),
        })
    return out


def create_campaign(display_name: str) -> str:
    slug = _unique_slug(display_name)
    now = datetime.now().isoformat(timespec="seconds")
    _atomic_write_json(_manifest_path(slug), {
        "display_name": display_name.strip() or slug,
        "created_at": now, "updated_at": now, "current": "", "versions": [],
    })
    return slug


def _new_version_filename(slug: str) -> str:
    base = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    name, n = f"{base}.json", 2
    while (_campaign_dir(slug) / name).exists():
        name, n = f"{base}-{n}.json", n + 1
    return name


def add_version(slug: str, doc: dict, label: str | None = None) -> str:
    if not _campaign_dir(slug).exists():
        raise FileNotFoundError(f"campaign not found: {slug}")
    fname = _new_version_filename(slug)
    speakers_io.save_speakers_json(str(_campaign_dir(slug) / fname), doc)
    m = _load_manifest(slug)
    now = datetime.now().isoformat(timespec="seconds")
    m.setdefault("versions", []).append({"file": fname, "created_at": now, "label": label})
    m["current"] = fname
    m["updated_at"] = now
    _atomic_write_json(_manifest_path(slug), m)
    return fname


def list_versions(slug: str) -> list[dict]:
    return list(_load_manifest(slug).get("versions", []))


def version_path(slug: str, version_file: str) -> Path:
    return _campaign_dir(slug) / version_file


def current_version_path(slug: str) -> Path:
    cur = _load_manifest(slug).get("current", "")
    if not cur:
        raise FileNotFoundError(f"campaign has no versions: {slug}")
    return version_path(slug, cur)


def get_version_doc(slug: str, version_file: str) -> dict:
    return speakers_io.load_speakers_json(str(version_path(slug, version_file)))


def get_current_doc(slug: str) -> dict:
    return speakers_io.load_speakers_json(str(current_version_path(slug)))


def set_current(slug: str, version_file: str) -> None:
    if not version_path(slug, version_file).exists():
        raise FileNotFoundError(version_file)
    m = _load_manifest(slug)
    m["current"] = version_file
    m["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _atomic_write_json(_manifest_path(slug), m)


def rename_campaign(slug: str, new_display_name: str) -> str:
    new_slug = _unique_slug(new_display_name)
    shutil.move(str(_campaign_dir(slug)), str(_campaign_dir(new_slug)))
    m = _load_manifest(new_slug)
    m["display_name"] = new_display_name.strip() or new_slug
    m["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _atomic_write_json(_manifest_path(new_slug), m)
    return new_slug


def delete_campaign(slug: str) -> None:
    shutil.rmtree(_campaign_dir(slug), ignore_errors=True)


def import_file(path: str, label: str = "imported") -> str:
    doc = speakers_io.load_speakers_json(path)
    name = (doc.get("campaign") or "").strip() or Path(path).stem
    slug = create_campaign(name)
    add_version(slug, doc, label=label)
    return slug


def export_version(slug: str, version_file: str, dest_path: str) -> None:
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(version_path(slug, version_file), dest)
```

- [ ] **Step 4:** `.venv\Scripts\python -m pytest tests/unit/test_library.py -v` → all PASS. `ruff check app/core/library.py tests/unit/test_library.py` clean.
- [ ] **Step 5: Commit** `feat: add campaign speakers library engine (app.core.library)`.

---

### Task 2: `CampaignPicker` widget — `app/ui/campaign_picker.py`

**Files:** Create `app/ui/campaign_picker.py`; Test `tests/unit/test_campaign_picker.py` (gui-marked where Tk needed).

The widget replaces the "speakers.json:" browse row in the consuming tabs. It exposes a uniform **path** accessor so downstream `speakers_io.load_speakers_json(path)` is unchanged.

- [ ] **Step 1: Write the widget** (`app/ui/campaign_picker.py`):

```python
"""Reusable 'Campaign ▾' picker that yields a speakers.json file PATH —
either a library campaign's current-version file or a loose file the user
browses ('Use a file instead…'). Downstream code loads by path, unchanged."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import library, speakers_io
from app.ui.theme import BTN_GHOST, S_2, S_3


class CampaignPicker(ttk.Frame):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self._on_change = on_change
        self._file_path: str | None = None  # set when using a loose file
        self._slug_by_label: dict[str, str] = {}

        ttk.Label(self, text="Campaign:").grid(row=0, column=0, sticky="w", padx=(0, S_2))
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.var, state="readonly", width=34)
        self.combo.grid(row=0, column=1, sticky="ew", padx=S_2)
        self.combo.bind("<<ComboboxSelected>>", self._on_combo)
        ttk.Button(self, text="Use a file instead…", style=BTN_GHOST,
                   command=self._browse_file).grid(row=0, column=2, padx=(S_3, 0))
        self.columnconfigure(1, weight=1)
        self.refresh()

    def refresh(self) -> None:
        rows = library.list_campaigns()
        self._slug_by_label = {}
        labels = []
        for r in rows:
            label = f"{r['display_name']} ({r['version_count']}v)"
            self._slug_by_label[label] = r["slug"]
            labels.append(label)
        self.combo["values"] = labels
        # keep selection if still present; else default to last_campaign
        if self.var.get() not in labels:
            last = config.load_config().get("last_campaign", "")
            match = next((lbl for lbl, slug in self._slug_by_label.items() if slug == last), None)
            self.var.set(match or (labels[0] if labels else ""))
        self._file_path = None

    def _on_combo(self, _e=None):
        self._file_path = None
        slug = self.selected_slug()
        if slug:
            cfg = config.load_config()
            cfg["last_campaign"] = slug
            config.save_config(cfg)
        if self._on_change:
            self._on_change()

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select speakers.json", initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        config.set_last_dir("json", path)
        self._file_path = path
        self.var.set(f"(file) {path}")
        if self._on_change:
            self._on_change()

    def selected_slug(self) -> str | None:
        if self._file_path:
            return None
        return self._slug_by_label.get(self.var.get())

    def selected_path(self) -> str | None:
        """The speakers.json path to load (loose file, or the campaign's current version)."""
        if self._file_path:
            return self._file_path
        slug = self.selected_slug()
        if not slug:
            return None
        try:
            return str(library.current_version_path(slug))
        except FileNotFoundError:
            return None  # campaign has no versions yet
```

- [ ] **Step 2: Test** (`tests/unit/test_campaign_picker.py`): a `@pytest.mark.gui` test that creates a campaign + version, builds the picker under a `tk.Tk()` (skip on `TclError`), and asserts `selected_path()` returns the current version file; and that `selected_slug()` is None after `_file_path` is set. (Mirror the smoke-fixture skip pattern.)
- [ ] **Step 3:** run gui test (passes on Windows), ruff clean. **Commit** `feat: add reusable CampaignPicker widget`.

---

### Task 3: `CampaignsTab` — the management home — `app/ui/campaigns_tab.py`

**Files:** Create `app/ui/campaigns_tab.py`; smoke coverage folded into Task 8.

- [ ] **Step 1:** Build `CampaignsTab(ttk.Frame)` with `__init__(self, master, app_window)` following the existing tab pattern (design-system styles, `on_show()` refresh). Layout:
  - Left: `ttk.Treeview`/`Listbox` of campaigns (from `library.list_campaigns()`), a search `Entry`, and a "New campaign" button (prompts for a name → `library.create_campaign`).
  - Right (on selection): summary labels (display name, campaign/context + speaker count from `library.get_current_doc`), a versions list (`library.list_versions`, current marked), and buttons wired to: `set_current`, `export_version` (→ `asksaveasfilename`), **Edit** (`self.app.build_profile_tab.load_campaign(slug)` + `self.app.jump_to_tab(<build profile index>)`), `rename_campaign` (prompt), `delete_campaign` (confirm), and **Import existing .json…** (`askopenfilename` → `library.import_file` → refresh).
  - `on_show()` re-reads the campaign list (so it reflects saves from other tabs).
- [ ] **Step 2:** Headless construct check + ruff. **Commit** `feat: add Campaigns management tab`.

(Full widget code is straightforward ttk; mirror `build_profile_tab.py`'s structure for the editor/list panes and `history_tab.py` for the master-detail layout. Keep methods small: `_refresh_list`, `_on_select`, `_new`, `_set_current`, `_export`, `_edit`, `_rename`, `_delete`, `_import`.)

---

### Task 4: Tab order + config — `app_window.py`, `config.py`

**Files:** Modify `app/ui/app_window.py`, `app/config.py`; extend `tests/smoke/test_app_smoke.py`.

- [ ] **Step 1:** `config.py` → add `"last_campaign": "",` to `DEFAULT_CONFIG`.
- [ ] **Step 2:** `app_window.py`:
  - import + construct `self.campaigns_tab = CampaignsTab(self.notebook, self)`.
  - Insert it **first** in `_tab_specs`: `(self.campaigns_tab, "1. Campaigns", "campaigns")`, and renumber the rest to `"2. Discover" … "7. History"`.
  - Update the `Ctrl+1..N` loop to `range(1, 8)`.
  - Audit any index-based logic (`_current_tab`, `_menu_open_audio` jump-to-index, `jump_to_tab` call sites in other tabs — e.g. Build Profile's `jump_to_tab(2)` for Transcribe must become the new Transcribe index) and update.
- [ ] **Step 3:** Update `tests/smoke/test_app_smoke.py` `EXPECTED_LABELS` to the new 7-label order; add an assertion `app.campaigns_tab` exists. Run the smoke test (proves order + construction).
- [ ] **Step 4:** ruff + full suite green. **Commit** `feat: add Campaigns as the first tab; renumber tabs; last_campaign config`.

(The "campaigns" icon is optional — `_load_tab_icon` returns None gracefully if the asset is absent.)

---

### Task 5: Build Profile saves into the library

**Files:** Modify `app/ui/build_profile_tab.py`.

Build Profile already has `self.campaign_var` (campaign name) and builds `doc` via `profiles_to_speakers_doc`. Change **Save** to write a new version into the campaign (create the campaign if needed), keeping a separate **Export a copy…** that retains the old `asksaveasfilename` → `save_speakers_json` behavior.

- [ ] **Step 1:** Add a "Save to library" primary action whose handler:
  - validates as today; builds `doc`;
  - resolves the campaign: find an existing campaign whose `display_name` matches `campaign_var` (case-insensitive) via `library.list_campaigns()`, else `library.create_campaign(campaign_var)`;
  - `library.add_version(slug, doc)`; set `config.last_campaign = slug`;
  - keep the existing DB-session persistence block;
  - success message naming the campaign + version.
- [ ] **Step 2:** Repurpose the existing `_save`/`_browse_out` as **"Export a copy…"** (unchanged file-save path).
- [ ] **Step 3:** Add `load_campaign(self, slug)` used by Campaigns-tab "Edit": loads `library.get_current_doc(slug)` into the editors + sets `campaign_var`.
- [ ] **Step 4:** Headless construct + the existing Build-Profile behavior unaffected; ruff; full suite green. **Commit** `feat: Build Profile saves speaker profiles into the campaign library`.

---

### Task 6: Consuming tabs use the picker — Transcribe / Summarize / Refine

**Files:** Modify `app/ui/transcribe_tab.py`, `app/ui/summarize_tab.py`, `app/ui/refine_tab.py`.

Each tab currently has a "speakers.json:" label + readonly entry + Browse button, and stores `self.speakers_path` (used downstream via `speakers_io.load_speakers_json`).

- [ ] **Step 1 (each tab):** Replace that row with `self.picker = CampaignPicker(self, on_change=self._on_picker_change)` gridded in the same cell; delete the old `_browse_speakers` button/entry. Add `_on_picker_change` → `self.speakers_path = self.picker.selected_path()` and refresh enable-state.
- [ ] **Step 2:** Anywhere the tab read `self.speakers_path` for "is one selected?", use `self.picker.selected_path()`. Keep all downstream `load_speakers_json(self.speakers_path)` calls as-is.
- [ ] **Step 3 (Refine only):** in the "accept changes" handler, after producing the improved `doc`: if `self.picker.selected_slug()` is not None → `library.add_version(slug, doc, label="refined")` (a new version, preserving history); else (loose file) keep the existing in-place `save_speakers_json(self.speakers_path, doc)` + `.bak`.
- [ ] **Step 4:** `on_show()` of each tab calls `self.picker.refresh()` so newly-saved campaigns appear. Headless construct + ruff + full suite green. **Commit** `feat: campaign picker in Transcribe/Summarize/Refine; Refine appends a version`.

---

### Task 7: Migration — one-time import prompt

**Files:** Modify `app/ui/app_window.py` (or `campaigns_tab.py`); `app/config.py`.

- [ ] **Step 1:** `config.py` → add `"library_import_prompted": False,` to `DEFAULT_CONFIG`.
- [ ] **Step 2:** On first run after the feature ships, if `not library.list_campaigns()` and `not cfg["library_import_prompted"]` and a `last_speakers_json` file exists, show a one-time dialog offering to import it → `library.import_file(last_speakers_json)`. Persist `library_import_prompted = True` regardless of choice. (The Campaigns tab's "Import existing .json…" remains the always-available path.)
- [ ] **Step 3:** Headless construct + ruff. **Commit** `feat: one-time prompt to import the last speakers.json into the library`.

---

### Task 8: Final smoke + green + manual

**Files:** `tests/smoke/test_campaigns.py` (new).

- [ ] **Step 1:** Smoke (`@pytest.mark.gui`): construct AppWindow (db.init_db, check_gpu stub); assert `campaigns_tab` builds and `EXPECTED_LABELS` order; create a campaign + version via `library`, then assert each consuming tab's `picker.refresh()` lists it and `selected_path()` resolves to the version file.
- [ ] **Step 2:** Full suite + ruff green.
- [ ] **Step 3: Manual** (`run_dev.bat`): create a campaign in Build Profile (Save to library) → see it in Campaigns tab with a version → pick it in Transcribe/Summarize → Refine accept adds a v2 → Set current to v1 → Export a copy → Import a loose file. Confirm "Use a file instead…" still works.
- [ ] **Step 4: Commit** `test: smoke-test Campaigns tab + picker integration`.

---

## Self-Review (during planning)
- **Spec coverage:** engine (Task 1) ✔; Campaigns tab (3) ✔; picker (2) ✔; Build Profile save→version (5) ✔; consuming pickers + Refine→version (6) ✔; tab-first + config (4) ✔; explicit import + one-time prompt (7) ✔; export-anywhere preserved (5/3) ✔; auto-keep history (engine immutable versions) ✔; manifest recovery + atomic writes (1) ✔.
- **No placeholders:** engine + picker fully coded; UI tabs (3/5/6/7) are concrete method-level tasks with exact targets + the picker contract + smoke guards — the repetitive tab code follows the one documented pattern, finalized against rebased `main`.
- **Type/name consistency:** `slug`, `add_version`, `current_version_path`, `selected_path`/`selected_slug`, `load_campaign`, `last_campaign`, `EXPECTED_LABELS` used consistently across tasks/tests.
- **CI lanes:** `test_library.py` is Tk-free (Ubuntu lane); picker/tab/smoke tests are `@pytest.mark.gui` (Windows lane).
- **Sequencing:** rebase pre-flight first (Theme/org-rename already on `main`); Task 4's tab-index change is guarded by the smoke `EXPECTED_LABELS`.
