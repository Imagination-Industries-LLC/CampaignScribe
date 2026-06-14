"""Test that AppWindow.report_callback_exception routes to config.log_exception."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


def _make_app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stubbed in test",
            "smi_gpu_name": None,
        },
    )
    try:
        from app.data import db

        db.init_db()
        from app.ui.app_window import AppWindow

        return AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")


def test_callback_exception_routes_to_log_exception(monkeypatch):
    from app import config
    from app.ui import app_window

    routed = []
    monkeypatch.setattr(config, "log_exception", lambda ctx, exc: routed.append(exc))
    monkeypatch.setattr(app_window.messagebox, "showerror", lambda *a, **k: None)

    app = _make_app(monkeypatch)
    app.withdraw()
    try:
        err = ValueError("boom in a callback")
        app.report_callback_exception(type(err), err, None)
        assert routed == [err]
    finally:
        app.destroy()
