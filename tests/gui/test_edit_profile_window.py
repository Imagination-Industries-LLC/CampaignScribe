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


def test_tracked_non_player_loads_into_roster_not_ignored(root):
    db.init_db()
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd", "",
        [
            {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
            {"display_name": "Narrator", "role": "Non-Player", "include_in_tracking": 1},
            {"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0},
        ],
        npcs=[],
    )
    library.add_version(slug, doc)
    from app.ui.edit_profile_window import EditProfileWindow
    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    try:
        # TV (ignore=true) is the only ignored voice; Narrator (tracked Non-Player) is in the roster
        assert len(win.ignored) == 1
        names = {ed.collect().get("display_name") for ed in win.editors}
        assert "Narrator" in names
        assert "Mike" in names
    finally:
        win.destroy()
