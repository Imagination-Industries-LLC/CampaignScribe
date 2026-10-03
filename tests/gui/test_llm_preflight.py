"""Pre-flight + banner use llm.provider_ready / not_ready_message; workers build one provider."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app import config

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


def test_banner_names_active_provider_and_hides_when_ready(app):
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    app._refresh_banner()
    app.update_idletasks()
    assert "Google Gemini" in app.banner_text.cget("text")
    assert app.banner.winfo_manager() == "pack"

    config.save_provider_key("gemini", "g-key")
    app._refresh_banner()
    app.update_idletasks()
    assert app.banner.winfo_manager() == ""


def test_summarize_start_blocks_with_provider_message(root, monkeypatch):
    from app.data import db
    from app.ui.summarize_tab import SummarizeTab

    db.init_db()
    cfg = config.load_config()
    cfg["llm_provider"] = "openrouter"
    config.save_config(cfg)
    shown = []
    monkeypatch.setattr(
        "app.ui.summarize_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = SummarizeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.transcript_files = ["t.txt"]
    tab._start()
    assert shown == ["Add your OpenRouter API key in Settings (⚙)."]


def test_refine_start_blocks_with_provider_message(root, monkeypatch):
    from app.ui.refine_tab import RefineTab

    shown = []
    monkeypatch.setattr(
        "app.ui.refine_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = RefineTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.speakers_doc = {"players": []}
    tab.audio_files = ["a.wav"]
    tab._start()
    assert shown == ["Add your Claude API key in Settings (⚙)."]
