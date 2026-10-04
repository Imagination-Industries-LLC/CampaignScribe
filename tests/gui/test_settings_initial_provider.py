"""SettingsDialog(initial_provider=...) starts on that provider without saving it."""

from __future__ import annotations

import threading
import tkinter as tk

import pytest

from app import config
from app.core import llm

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


def _open(root, **kw):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root, **kw)
    dlg.update_idletasks()
    return dlg


def test_opens_on_requested_provider(root):
    dlg = _open(root, initial_provider="gemini")
    try:
        assert dlg._llm_current == "gemini"
        assert dlg.llm_provider_var.get() == llm.PRESETS["gemini"].display_name
    finally:
        dlg.destroy()


def test_local_preselection_runs_detect_without_network(root, monkeypatch):
    from app.core.llm import local_detect

    calls = []

    def fake_detect(runtime_id, *, base_url=None, timeout_s=1.5):
        calls.append(runtime_id)
        return local_detect.DetectResult(runtime_id, False, [], "stub")

    monkeypatch.setattr(local_detect, "detect", fake_detect)
    dlg = _open(root, initial_provider="ollama")
    try:
        assert dlg._llm_current == "ollama"
        # Drain the threaded auto-detect so no callback fires on a destroyed dialog.
        for _ in range(100):
            dlg._poll_detect()
            dlg.update()
            if not dlg._llm_state["ollama"]["detecting"]:
                break
            threading.Event().wait(0.02)
        assert dlg._llm_state["ollama"]["detecting"] is False
        assert calls == ["ollama"]
    finally:
        dlg.destroy()


def test_cancel_leaves_configured_provider_unchanged(root):
    dlg = _open(root, initial_provider="gemini")
    dlg.destroy()  # Cancel = destroy without _save
    assert config.load_config()["llm_provider"] == "anthropic"


def test_save_after_preselection_persists_provider(root, monkeypatch):
    monkeypatch.setattr("app.ui.settings_dialog.messagebox.showerror", lambda *a, **k: None)
    monkeypatch.setattr("app.ui.settings_dialog.messagebox.showinfo", lambda *a, **k: None)
    dlg = _open(root, initial_provider="gemini")
    dlg._save()  # destroys the dialog on success
    assert config.load_config()["llm_provider"] == "gemini"


def test_unknown_provider_falls_back_to_configured(root):
    cfg = config.load_config()
    cfg["llm_provider"] = "openrouter"
    config.save_config(cfg)
    dlg = _open(root, initial_provider="nope")
    try:
        assert dlg._llm_current == "openrouter"
    finally:
        dlg.destroy()


def test_no_initial_provider_keeps_configured(root):
    dlg = _open(root)
    try:
        assert dlg._llm_current == "anthropic"
    finally:
        dlg.destroy()
