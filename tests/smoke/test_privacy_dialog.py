"""Headless smoke: Privacy dialog builds; the four API tabs carry a privacy note."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.core import privacy

pytestmark = pytest.mark.gui


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stub",
            "smi_gpu_name": None,
        },
    )
    from app.data import db

    db.init_db()
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    win.withdraw()
    win.update_idletasks()
    try:
        yield win
    finally:
        win.destroy()


def test_privacy_dialog_builds_and_shows_statement(app):
    from app.ui.app_window import PrivacyDialog

    dlg = None
    try:
        dlg = PrivacyDialog(app)
        app.update_idletasks()

        widgets: list = []

        def _collect(w):
            widgets.append(w)
            for child in w.winfo_children():
                _collect(child)

        _collect(dlg)
        text_widgets = [w for w in widgets if isinstance(w, tk.Text)]
        assert text_widgets, "PrivacyDialog should contain a Text widget"
        assert "Anthropic Claude API" in text_widgets[0].get("1.0", "end")
        assert "OpenRouter" in text_widgets[0].get("1.0", "end")
        assert "Ollama / LM Studio (local)" in text_widgets[0].get("1.0", "end")
    finally:
        if dlg is not None:
            dlg.destroy()


def test_api_tabs_have_privacy_notes_for_active_provider(app):
    from app import config

    assert app.transcribe_tab._privacy_note.cget("text") == privacy.note_samples(
        "Anthropic (Claude)"
    )
    assert app.refine_tab._privacy_note.cget("text") == privacy.note_samples("Anthropic (Claude)")
    assert app.summarize_tab._privacy_note.cget("text") == privacy.note_transcript(
        "Anthropic (Claude)"
    )

    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    for tab in (app.transcribe_tab, app.refine_tab, app.summarize_tab):
        tab.on_settings_changed()
    app.update_idletasks()
    assert "Google (Gemini)" in app.transcribe_tab._privacy_note.cget("text")
    assert "Google (Gemini)" in app.summarize_tab._privacy_note.cget("text")
