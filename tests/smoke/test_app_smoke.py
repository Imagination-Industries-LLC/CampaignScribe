"""Headless smoke test: AppWindow constructs, all tabs build, tab order is correct."""

from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui

# Expected display labels in display order. Update ONLY if the intended tab
# ordering changes — names are decoupled from module/class names by Group E.
EXPECTED_LABELS = [
    "1. Campaigns",
    "2. Discover",
    "3. Build Profile",
    "4. Transcribe",
    "5. Summarize",
    "6. Refine",
    "7. History",
]


@pytest.fixture
def app(monkeypatch):
    # Avoid importing torch / probing GPU during construction.
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stubbed in test",
            "smi_gpu_name": None,
        },
    )
    # Mirror main.py's startup contract: the DB must be initialized before the
    # window is built (a tab queries the sessions table during construction).
    # %APPDATA% is redirected to a tmp dir by the autouse isolate_appdata fixture.
    from app.data import db

    db.init_db()
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display available for Tk: {e}")
    win.withdraw()
    win.update_idletasks()
    try:
        yield win
    finally:
        win.destroy()


def test_app_window_constructs_with_seven_tabs(app):
    assert len(app.notebook.tabs()) == 7
    assert app.campaigns_tab.winfo_exists()


def test_tab_labels_in_expected_order(app):
    labels = [app.notebook.tab(i, "text") for i in range(len(app.notebook.tabs()))]
    assert labels == EXPECTED_LABELS


def test_each_tab_is_a_frame_widget(app):
    for widget, _label, _icon in app._tab_specs:
        assert widget.winfo_exists()


def test_on_tab_changed_does_not_raise(app):
    for i in range(len(app.notebook.tabs())):
        app.notebook.select(i)
        app.update_idletasks()
