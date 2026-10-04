"""Home shows an actionable empty state only when there is nothing at all."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.core import library
from app.data import db

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


def _shown(widget) -> bool:
    return widget.winfo_manager() == "grid"


def test_empty_library_shows_empty_state(app):
    home = app.home_tab
    from app.ui import home_tab

    assert home.title_var.get() == home_tab.EMPTY_TITLE == "No campaigns yet"
    assert home.summary_var.get() == home_tab.EMPTY_SUMMARY
    assert _shown(home.first_campaign_btn)
    assert not _shown(home.new_session_btn)


def test_create_button_creates_and_hides_empty_state(app, monkeypatch):
    home = app.home_tab
    monkeypatch.setattr("app.ui.home_tab.simpledialog.askstring", lambda *a, **k: "Strahd")
    home.first_campaign_btn.invoke()
    assert [r["display_name"] for r in library.list_campaigns()] == ["Strahd"]
    assert home.title_var.get() == "Strahd"
    assert not _shown(home.first_campaign_btn)
    assert _shown(home.new_session_btn)


def test_cancelled_name_keeps_empty_state(app, monkeypatch):
    home = app.home_tab
    monkeypatch.setattr("app.ui.home_tab.simpledialog.askstring", lambda *a, **k: None)
    home.new_campaign()
    assert home.title_var.get() == "No campaigns yet"


def test_existing_campaign_hidden_by_search_is_not_empty_state(app):
    library.create_campaign("Strahd")
    home = app.home_tab
    home.search_var.set("zzz")  # trace calls _refresh_campaigns
    assert home.title_var.get() == "Select a campaign"
    assert not _shown(home.first_campaign_btn)


def test_loose_sessions_mean_not_empty(app):
    db.create_session("Loose")
    home = app.home_tab
    home.on_show()
    assert home.title_var.get() != "No campaigns yet"
    assert not _shown(home.first_campaign_btn)


def test_empty_check_failure_is_logged_and_treated_as_not_empty(app, monkeypatch):
    from app import config

    home = app.home_tab

    def boom():
        raise RuntimeError("library exploded")

    monkeypatch.setattr("app.ui.home_tab.library.list_campaigns", boom)
    home._clear_detail()  # must not raise
    assert home.title_var.get() == "Select a campaign"
    assert not _shown(home.first_campaign_btn)
    log = (config.get_app_data_dir() / "errors.log").read_text(encoding="utf-8")
    assert "home empty-state check" in log
