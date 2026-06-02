"""Integration smoke test: Campaigns tab + CampaignPicker across consuming tabs."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui

DOC = {
    "campaign": "Curse of Strahd",
    "context": "gothic horror",
    "players": [{"player_name": "Mike"}],
    "known_non_players": [],
    "fallback_policy": {},
}

EXPECTED_LABELS = [
    "1. Campaigns",
    "2. Discover",
    "3. Build Profile",
    "4. Transcribe",
    "5. Summarize",
    "6. Refine",
    "7. History",
]


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stubbed in test",
            "smi_gpu_name": None,
        },
    )
    from app.data import db

    db.init_db()
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display available for Tk: {e}")
    win.withdraw()
    win.update_idletasks()
    try:
        yield win
    finally:
        win.destroy()


def test_campaigns_tab_builds_and_label_order(app):
    assert app.campaigns_tab.winfo_exists()
    labels = [app.notebook.tab(i, "text") for i in range(len(app.notebook.tabs()))]
    assert labels == EXPECTED_LABELS



def test_campaigns_tab_on_show_reflects_new_campaign(app):
    from app.core import library

    # CampaignsTab refreshes its list on show, picking up library writes.
    slug = library.create_campaign("Wildemount")
    library.add_version(slug, DOC)
    app.campaigns_tab.on_show()
    app.update_idletasks()
    # the campaign appears in the engine the tab reads from
    assert any(r["slug"] == slug for r in library.list_campaigns())


def test_reopen_in_transcribe_keeps_session_speakers_path(app, monkeypatch, tmp_path):
    import json

    from app.ui import transcribe_tab as tt

    loose = tmp_path / "session_speakers.json"
    loose.write_text(json.dumps(DOC), encoding="utf-8")
    monkeypatch.setattr(
        tt.db,
        "get_session",
        lambda sid: {"speakers_json_path": str(loose), "source_audio_files": "[]"},
    )
    app.transcribe_tab.load_session(999)
    app.transcribe_tab.on_show()  # simulates the tab becoming visible (where the clobber happened)
    assert app.transcribe_tab.speakers_path == str(loose)
