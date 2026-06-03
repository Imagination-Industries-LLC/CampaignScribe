"""Transcribe cold-start on-ramp: profile-less campaign -> offer Discover -> Edit Profile."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library
from app.data import db
from app.ui import transcribe_tab as tt
from app.ui.transcribe_tab import TranscribeTab

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


def test_transcribe_offers_discover_when_no_profile(root, monkeypatch, tmp_path):
    db.init_db()
    slug = library.create_campaign("Strahd")  # NO version -> no profile
    sid = db.create_session("Night 1", campaign_slug=slug)
    calls = {"edit": []}
    app = types.SimpleNamespace(
        notebook=None,
        open_edit_profile=lambda s, discover_audio=None: calls["edit"].append((s, discover_audio)),
    )
    tab = TranscribeTab(root, app)
    root.update_idletasks()
    audio = tmp_path / "s.mp3"
    audio.write_bytes(b"x")
    tab.load_for_session(db.get_session(sid))  # sets active_slug=slug, speakers_path=None
    tab.audio_files = [str(audio)]
    monkeypatch.setattr(tt.messagebox, "askyesno", lambda *a, **k: True)
    tab._start()
    # offered discover and routed to Edit Profile with the session audio; did NOT transcribe
    assert calls["edit"] == [(slug, str(audio))]
    assert tab._busy is False


def test_transcribe_no_profile_declined_does_nothing(root, monkeypatch, tmp_path):
    db.init_db()
    slug = library.create_campaign("Strahd")
    sid = db.create_session("Night 1", campaign_slug=slug)
    calls = {"edit": []}
    app = types.SimpleNamespace(
        notebook=None,
        open_edit_profile=lambda s, discover_audio=None: calls["edit"].append((s, discover_audio)),
    )
    tab = TranscribeTab(root, app)
    root.update_idletasks()
    tab.load_for_session(db.get_session(sid))
    tab.audio_files = [str(tmp_path / "s.mp3")]
    monkeypatch.setattr(tt.messagebox, "askyesno", lambda *a, **k: False)
    tab._start()
    assert calls["edit"] == []
    assert tab._busy is False
