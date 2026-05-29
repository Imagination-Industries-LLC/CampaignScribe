"""Headless smoke test: AppWindow constructs, all tabs build, tab order is correct."""
from __future__ import annotations

import tkinter as tk

import pytest

pytestmark = pytest.mark.gui

# Expected display labels in display order. Update ONLY if the intended tab
# ordering changes — names are decoupled from module/class names by Group E.
EXPECTED_LABELS = [
    "1. Discover",
    "2. Build Profile",
    "3. Transcribe",
    "4. Summarize",
    "5. Refine",
    "6. History",
]


@pytest.fixture
def app(monkeypatch):
    # Avoid importing torch / probing GPU during construction.
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {"recommendation": "cpu_unavailable", "torch_version": None,
                 "error": "stubbed in test", "smi_gpu_name": None},
    )
    try:
        from app.ui.app_window import AppWindow
        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display available for Tk: {e}")
    win.withdraw()
    win.update_idletasks()
    yield win
    win.destroy()


def test_app_window_constructs_with_six_tabs(app):
    assert len(app.notebook.tabs()) == 6


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
