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
