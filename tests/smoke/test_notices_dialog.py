"""Headless smoke: the third-party notices dialog renders the bundled text."""

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


def test_notices_dialog_shows_text(app):
    from app.ui.app_window import NoticesDialog

    dlg = NoticesDialog(app)
    app.update_idletasks()
    try:
        texts = []

        def _walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Text):
                    texts.append(c.get("1.0", "end"))
                _walk(c)

        _walk(dlg)
        assert texts and "pyannote" in texts[0]
    finally:
        dlg.destroy()
