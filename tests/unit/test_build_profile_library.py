"""Build Profile saves into the library + load_campaign round-trip."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library

pytestmark = pytest.mark.gui

DOC = {
    "campaign": "Strahd",
    "context": "gothic",
    "players": [
        {
            "player_name": "Mike",
            "role": "Player",
            "character_name": "Wellbrix",
            "source_speaker_id": "SPEAKER_01",
            "speech_patterns": [],
            "notes": "",
        }
    ],
    "known_non_players": [],
    "fallback_policy": {},
}


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


def test_load_campaign_then_save_creates_new_version(root, monkeypatch):
    from app.data import db
    from app.ui import build_profile_tab as bpt

    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    tab = bpt.BuildProfileTab(root, types.SimpleNamespace(notebook=None, transcribe_tab=None))
    root.update_idletasks()
    tab.load_campaign(slug)
    assert tab.campaign_var.get() == "Strahd"
    assert len(tab.editors) >= 1
    monkeypatch.setattr(bpt.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(bpt.messagebox, "showerror", lambda *a, **k: None)
    out_slug = tab._save_to_library()
    assert out_slug == slug
    assert len(library.list_versions(slug)) == 2  # original + the save


def test_load_campaign_with_no_versions_does_not_crash(root):
    from app.data import db
    from app.ui import build_profile_tab as bpt

    db.init_db()
    slug = library.create_campaign("Empty")  # zero versions
    tab = bpt.BuildProfileTab(root, types.SimpleNamespace(notebook=None, transcribe_tab=None))
    root.update_idletasks()
    tab.load_campaign(slug)  # must not raise
    assert tab.campaign_var.get() == "Empty"
    assert tab.editors == []  # empty, ready to build
