"""Headless smoke: theme rebuild plumbing + busy guard."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.ui import theme

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def restore_variant():
    prev = theme._active_variant
    yield
    theme.set_theme_variant(prev)


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
        try:
            win.destroy()
        except tk.TclError:
            pass


def test_fresh_window_not_requesting_rebuild(app):
    assert app._rebuild_requested is False


def test_any_tab_busy_reflects_tab_state(app):
    assert app._any_tab_busy() is False
    app.discover_tab._busy = True
    assert app._any_tab_busy() is True
    app.discover_tab._busy = False


def test_request_rebuild_sets_flag(app):
    app.request_rebuild()
    assert app._rebuild_requested is True


def test_handle_theme_change_blocks_while_busy(app, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "app.ui.app_window.messagebox.showinfo",
        lambda *a, **k: shown.setdefault("msg", True),
    )
    app.transcribe_tab._busy = True
    app._handle_theme_change()
    assert app._rebuild_requested is False  # blocked
    assert shown.get("msg") is True
    app.transcribe_tab._busy = False


def test_handle_theme_change_triggers_rebuild_when_idle(app):
    assert not app._any_tab_busy()
    app._handle_theme_change()
    assert app._rebuild_requested is True
