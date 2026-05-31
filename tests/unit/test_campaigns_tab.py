"""Gui smoke for CampaignsTab built standalone with a stub app."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library

pytestmark = pytest.mark.gui

DOC = {
    "campaign": "Strahd",
    "context": "gothic",
    "players": [{"player_name": "Mike"}],
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


def test_campaigns_tab_lists_and_shows_versions(root):
    from app.ui.campaigns_tab import CampaignsTab

    slug = library.create_campaign("Strahd")
    library.add_version(slug, DOC)
    library.add_version(slug, DOC, label="s4")
    stub_app = types.SimpleNamespace(notebook=None, build_profile_tab=None)
    tab = CampaignsTab(root, stub_app)
    root.update_idletasks()
    assert slug in tab._slugs
    tab._selected_slug = slug
    tab._show_detail(slug)
    # two versions should be in the treeview
    assert len(tab.versions.get_children()) == 2


def test_campaigns_tab_empty_is_safe(root):
    from app.ui.campaigns_tab import CampaignsTab

    stub_app = types.SimpleNamespace(notebook=None, build_profile_tab=None)
    tab = CampaignsTab(root, stub_app)
    root.update_idletasks()
    assert tab._slugs == []
    assert tab._selected_slug is None
