# Feature Spec — Campaign Speakers Library

- **Status:** Designed, not yet implemented
- **Date:** 2026-05-30
- **Source:** Brainstorm 2026-05-30 (new capability, not part of the original 14-spec roadmap)
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`)
- **Owner intent:** Users shouldn't have to find/juggle multiple `speakers.json` files across campaigns or iterations. The app should organize and preserve them — while still letting users save a copy anywhere they want.

## Problem
Today `speakers.json` is a free-floating file. The user **saves** it via an OS "Save as…" dialog in Build Profile, and **re-selects** it via "browse" dialogs every time in Transcribe / Summarize / Refine (Refine overwrites it in place with a single `.bak`). Config only remembers the *last* path. Anyone running multiple campaigns, or iterating a profile over several sessions, ends up manually tracking a pile of `.json` files on disk.

## Decisions (brainstorm 2026-05-30)
1. **Model:** Campaign → versions. The library is a set of **campaigns**; each campaign owns a speaker profile with **auto-kept version history** (latest = "current").
2. **Storage:** an app-managed **folder tree of real `.json` files** (not the DB), so it stays human-browsable + recoverable and reuses the existing file-based `speakers_io`.
3. **Versioning:** **auto-keep history** — each save (Build Profile save; accepting Refine changes) writes a new timestamped version; older versions are preserved behind a history view; nothing is overwritten/lost.
4. **UI home:** a **new "Campaigns" tab**, placed **first** in the tab order (it's what you set up first).
5. **Consuming tabs:** Transcribe / Summarize / Refine get a **"Campaign ▾" picker** (uses the campaign's current version), with a **"Use a file instead…"** escape hatch to still browse an arbitrary `.json`.
6. **Migration:** **explicit import only** — library starts empty; an "Import existing .json…" action pulls a loose file in; plus a one-time gentle prompt offering to import the last-used `speakers.json`. No disk scanning.

## Disk layout
App-managed, under the existing app-data dir:
```
%APPDATA%\CampaignScribe\library\
   <campaign-slug>\
      manifest.json          # display name, created/updated, version list, current-version pointer
      2026-05-30T141233.json # an immutable version (a normal speakers.json doc)
      2026-05-28T090210.json
   <another-campaign-slug>\
      ...
```
- A **version file** is an ordinary `speakers.json` document (existing `speakers_io` schema). Versions are immutable — a "new version" is a new file, never an overwrite.
- A **manifest.json** per campaign records: `display_name`, `created_at`, `updated_at`, `current` (the current version's filename), and `versions` (list of `{file, created_at, label?}`). The manifest is the campaign's metadata; the version files are the content.
- "Export a copy anywhere" = copy the chosen version file to a user-picked path (the existing save-as ability, retained).
- The SQLite DB is **untouched**; sessions may optionally record which campaign + version they used (a later enhancement — not required by this spec).

## Components

### New — `app/core/library.py` (Tk-free)
The library engine, file-based, no Tk. Responsibilities (well-defined interface; unit-tested):
- `library_root() -> Path` — `%APPDATA%\CampaignScribe\library`, created on demand.
- `slugify(name) -> str` — campaign display name → safe folder slug; deterministic; handles collisions by disambiguating (e.g. append `-2`).
- `list_campaigns() -> list[Campaign]` — read each subfolder's manifest; return lightweight campaign records (slug, display name, current version, #versions, updated_at).
- `create_campaign(display_name) -> Campaign` — make the folder + an empty manifest.
- `add_version(slug, doc, label=None) -> version_id` — write a new timestamped version file (atomic, reuse `speakers_io.save_speakers_json` semantics), update manifest, set it current.
- `get_current_doc(slug) -> dict` / `get_version_doc(slug, version_id) -> dict` — load a version's `speakers.json` content.
- `set_current(slug, version_id)` — move the current pointer (no file rewrite).
- `list_versions(slug) -> list[Version]`.
- `rename_campaign(slug, new_display_name)` / `delete_campaign(slug)` (delete = remove folder; confirmed in UI).
- `import_file(path, label="imported") -> Campaign` — read a loose `speakers.json`, derive the campaign from its `campaign` field (fallback to filename), create/append a version.
- `export_version(slug, version_id, dest_path)` — copy a version file to an arbitrary path.
All writes are atomic (temp + `os.replace`, matching the existing `speakers_io` pattern); the manifest write is atomic too.

### New — `app/ui/campaigns_tab.py` (`CampaignsTab`) — the home
- **Left:** campaign list + search box + "New campaign".
- **Right (selected campaign):** summary (display name, campaign/context, # speakers in current), a **version history** list (current marked, timestamps + optional labels), and actions: **Set current**, **Export copy…**, **Edit** (opens the current version in Build Profile), **Rename**, **Delete** (confirm), **Import existing .json…**.
- Follows the existing tab pattern (`ttk.Frame`, `__init__(self, master, app_window)`, `on_show()` refresh, design-system styles). Registered in `app_window.py`'s `_tab_specs` **first** (before Discover); icon optional.

### New — `app/ui/campaign_picker.py` (reusable widget)
A small composite widget the consuming tabs embed in place of the "speakers.json:" browse row:
- A **"Campaign ▾"** readonly combobox listing library campaigns (shows current-version hint), bound to a `StringVar`.
- A **"Use a file instead…"** button → the existing `askopenfilename`, which sets an explicit file path mode.
- Exposes a uniform accessor (e.g. `selected_speakers_path()` / `selected_doc()`) so tabs don't care whether the source is a library campaign or a loose file.

### Changed — Build Profile (`build_profile_tab.py`)
- **Save** writes a **new version into the selected/created campaign** via `library.add_version(...)` (replacing the raw "Save as…" as the primary action). A campaign selector/creator is shown (pick existing or "New campaign").
- Keeps a separate **"Export a copy…"** for saving a standalone file elsewhere.
- The existing "load an existing speakers.json" entry point remains (and can offer "add to library").

### Changed — Transcribe / Summarize / Refine
- Replace the "speakers.json:" browse field with the **`CampaignPicker`** widget.
- **Refine** "accept changes" calls `library.add_version(...)` on the selected campaign (a **new version**, preserving history) instead of overwriting the file in place. If the source is a loose file (escape hatch), it falls back to the current overwrite-with-`.bak` behavior.

### Changed — config / app_window
- `app_window.py`: add `CampaignsTab` as the first entry in `_tab_specs`; update tab numbering/labels ("1. Campaigns", "2. Discover", … "7. History"); update the `Ctrl+1..N` shortcuts and `_menu_open_audio`/`_current_tab` index assumptions accordingly.
- `config.py`: a `last_campaign` key (remember the last-picked campaign slug) replacing/augmenting `last_speakers_json` for the picker default; keep `last_speakers_json` for the file escape-hatch.

## Data flow
- **Build a profile → save:** Discover/Build Profile produce a doc → user picks/creates a campaign → `add_version` → new version becomes current → appears in Campaigns tab history.
- **Use in Transcribe/Summarize:** pick a campaign → tab loads that campaign's **current** version doc → runs as today. (Or "Use a file instead…" for a loose file.)
- **Refine → accept:** loads the campaign's current doc → produces improvements → on accept, `add_version` writes a new version (history grows; current advances).
- **Import:** "Import existing .json…" → `import_file` → campaign created/updated from the file's `campaign` field.
- **Export:** "Export copy…" → `export_version` to a user-chosen path.

## Error handling
- Missing/corrupt manifest → treat the campaign folder defensively (rebuild manifest from the version files present; never crash the tab).
- Corrupt version file → surface a clear error; other versions remain usable.
- Slug collisions / illegal campaign names → `slugify` disambiguates; empty name rejected with a message.
- Atomic writes everywhere so a crash mid-save can't corrupt a manifest or version.
- Deleting a campaign is confirmed; export never deletes.

## Testing plan
- **Unit (`app/core/library.py`, Tk-free, Ubuntu lane):** create/list campaigns; add_version → current advances + history grows; set_current; get_current/version doc round-trip; slugify + collision disambiguation; import_file derives campaign from the doc's `campaign` field; export copies bytes; corrupt-manifest recovery; atomic-write leaves no temp.
- **Smoke (`@pytest.mark.gui`, Windows lane):** Campaigns tab builds + lists campaigns; CampaignPicker populates + switching selects a campaign; Build Profile save creates a version; (headless) the picker's uniform accessor returns the right doc/path.

## Out of scope (deferred)
- Storing the library in the SQLite DB (chose files).
- Auto-scanning the disk for loose `speakers.json` files (explicit import only).
- A live OS-folder watcher / external-edit sync.
- Cross-device library sync.
- Recording campaign+version onto each saved session row in the DB (nice future enhancement; not required here).

## Dependencies / sequencing
- Independent of the Phase 1 Feedback/Support Hub. Touches `app_window.py` tab order + the four speaker tabs + config — coordinate with the in-flight Theme PR (#15) which also edits `app_window.py`/`config.py`/Settings (rebase after it merges).
- No new third-party dependencies.
