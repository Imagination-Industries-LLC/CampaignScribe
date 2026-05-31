"""Tests for app.ui.campaign_picker.CampaignPicker (gui-marked)."""

from __future__ import annotations

import tkinter as tk

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


def test_picker_lists_campaigns_and_resolves_current_path(root):
    from app.ui.campaign_picker import CampaignPicker

    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    picker = CampaignPicker(root)
    root.update_idletasks()
    assert picker.selected_slug() == slug
    assert picker.selected_path() == str(library.current_version_path(slug))


def test_picker_empty_library_has_no_selection(root):
    from app.ui.campaign_picker import CampaignPicker

    picker = CampaignPicker(root)
    root.update_idletasks()
    assert picker.selected_slug() is None
    assert picker.selected_path() is None


def test_picker_file_mode_clears_slug(root, monkeypatch, tmp_path):
    from app.ui import campaign_picker

    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    picker = campaign_picker.CampaignPicker(root)
    f = tmp_path / "loose.json"
    import json

    f.write_text(json.dumps(DOC), encoding="utf-8")
    monkeypatch.setattr(campaign_picker.filedialog, "askopenfilename", lambda **k: str(f))
    picker._browse_file()
    assert picker.selected_slug() is None  # file mode
    assert picker.selected_path() == str(f)
