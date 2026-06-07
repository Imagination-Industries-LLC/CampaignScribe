# tests/gui/test_transcribe_count_handoff.py
import tkinter as tk
import types

import pytest

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


def _campaign(name, players):
    from app.core import library, speakers_io

    slug = library.create_campaign(name)
    doc = speakers_io.profiles_to_speakers_doc(
        name,
        "",
        [{"display_name": p, "role": "Player", "include_in_tracking": 1} for p in players],
        npcs=[],
    )
    library.add_version(slug, doc)
    return slug


def test_start_transcription_hands_count_to_stage(root):
    from app.data import db
    from app.ui.session_view import SessionView

    db.init_db()
    slug = _campaign("Strahd", ["Ann", "Bob", "Cara"])
    sid = db.create_session("Night 1", campaign_slug=slug)

    captured = {}
    app = types.SimpleNamespace(
        notebook=None,
        open_home=lambda: None,
        open_session_stage=lambda s, stage, run_params=None: captured.update(
            sid=s, stage=stage, run_params=run_params
        ),
    )
    view = SessionView(root, app, sid)
    root.update_idletasks()
    try:
        view.count_spin_var.set(4)
        view._start_transcription()
        assert captured["stage"] == "transcribe"
        assert captured["run_params"] == {"expected_count": 4}
    finally:
        view.destroy()
