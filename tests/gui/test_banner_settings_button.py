"""The setup banner has an Open Settings button; open_settings passes initial_provider."""

from __future__ import annotations

import tkinter as tk

import pytest

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


def test_banner_button_opens_settings(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "open_settings", lambda *a, **k: calls.append((a, k)))
    assert app.banner_settings_btn.cget("text") == "Open Settings"
    app.banner_settings_btn.invoke()
    assert calls == [((), {})]


def test_open_settings_passes_initial_provider(app, monkeypatch):
    seen = []

    class _FakeSettings(tk.Toplevel):
        def __init__(self, master, initial_provider=None):
            super().__init__(master)
            seen.append(initial_provider)
            self.after(0, self.destroy)

    monkeypatch.setattr("app.ui.app_window.SettingsDialog", _FakeSettings)
    app.open_settings(initial_provider="ollama")
    app.open_settings()
    assert seen == ["ollama", None]
