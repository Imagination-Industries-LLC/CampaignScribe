"""Each consuming tab embeds a CampaignPicker and resolves a campaign path."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library

pytestmark = pytest.mark.gui

DOC = {
    "campaign": "Strahd",
    "context": "",
    "players": [],
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


def _stub_app():
    return types.SimpleNamespace(notebook=None)


@pytest.mark.parametrize(
    "modpath,clsname",
    [
        ("app.ui.transcribe_tab", "TranscribeTab"),
        ("app.ui.summarize_tab", "SummarizeTab"),
        ("app.ui.refine_tab", "RefineTab"),
    ],
)
def test_tab_has_picker_resolving_campaign(root, modpath, clsname):
    import importlib

    from app.data import db

    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    mod = importlib.import_module(modpath)
    tab = getattr(mod, clsname)(root, _stub_app())
    root.update_idletasks()
    assert hasattr(tab, "picker")
    tab.picker.refresh()
    # selecting the campaign resolves to its current version file
    assert tab.picker.selected_path() == str(library.current_version_path(slug))


def test_picker_select_by_slug(root):
    from app.data import db
    from app.ui.campaign_picker import CampaignPicker

    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    other = library.create_campaign("Wildemount")
    library.add_version(other, DOC)
    picker = CampaignPicker(root)
    root.update_idletasks()
    assert picker.select_by_slug(other) is True
    assert picker.selected_slug() == other
    assert picker.select_by_slug("nonexistent") is False


def test_refine_on_show_seeds_speakers_doc(root):
    import types

    from app.data import db
    from app.ui.refine_tab import RefineTab

    db.init_db()
    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    from app import config as _cfg

    c = _cfg.load_config()
    c["last_campaign"] = slug
    _cfg.save_config(c)
    tab = RefineTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.on_show()
    assert tab.speakers_path == str(library.current_version_path(slug))
    assert tab.speakers_doc is not None  # seeded, not None


def test_picker_refresh_preserves_file_selection(root, tmp_path):
    import json

    from app.data import db
    from app.ui.campaign_picker import CampaignPicker

    db.init_db()
    library.create_campaign("Strahd")  # a campaign exists so refresh has a default
    f = tmp_path / "loose.json"
    f.write_text(json.dumps({"campaign": "Loose", "players": []}), encoding="utf-8")
    picker = CampaignPicker(root)
    root.update_idletasks()
    assert picker.select_file(str(f)) is True
    assert picker.selected_slug() is None
    assert picker.selected_path() == str(f)
    picker.refresh()  # must NOT drop the loose-file selection
    assert picker.selected_slug() is None
    assert picker.selected_path() == str(f)


def test_picker_select_file_rejects_unreadable(root, tmp_path):
    from app.data import db
    from app.ui.campaign_picker import CampaignPicker

    db.init_db()
    picker = CampaignPicker(root)
    root.update_idletasks()
    bad = tmp_path / "nope.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert picker.select_file(str(bad)) is False
    assert picker.selected_path() is None  # state unchanged
