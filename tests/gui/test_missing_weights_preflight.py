"""Missing diarization weights fail fast with the full remedy before any worker starts."""

from __future__ import annotations

import threading
import tkinter as tk
import types

import pytest

from app import config
from app.core import models

pytestmark = pytest.mark.gui

MSG = "Speaker-diarization model files are missing. Reinstall CampaignScribe to restore them."


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


def _arm(monkeypatch):
    cfg = config.load_config()
    cfg["llm_provider"] = "anthropic"
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")

    def _missing():
        raise models.MissingModelError(MSG)

    monkeypatch.setattr(models, "diarization_dir", _missing)
    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self, *a, **k: started.append(1))
    return [], started


def test_transcribe_start_shows_full_remedy(root, monkeypatch):
    from app.data import db
    from app.ui.transcribe_tab import TranscribeTab

    db.init_db()
    shown, started = _arm(monkeypatch)
    monkeypatch.setattr(
        "app.ui.transcribe_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = TranscribeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.speakers_doc = {"players": []}
    tab.audio_files = ["a.wav"]
    tab._start()
    assert shown and "Reinstall CampaignScribe" in shown[-1]
    assert started == []


def test_refine_start_shows_full_remedy(root, monkeypatch):
    from app.ui.refine_tab import RefineTab

    shown, started = _arm(monkeypatch)
    monkeypatch.setattr(
        "app.ui.refine_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = RefineTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.speakers_doc = {"players": []}
    tab.audio_files = ["a.wav"]
    tab._start()
    assert shown and "Reinstall CampaignScribe" in shown[-1]
    assert started == []
