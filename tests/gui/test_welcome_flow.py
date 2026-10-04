"""Startup prompts: library import, then the one-time welcome, then the first-campaign offer."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
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
        try:
            win.destroy()
        except tk.TclError:
            pass  # a test may already have closed the main window


@pytest.fixture
def rec(monkeypatch, app):
    """Record welcome shows, Settings opens, yes/no prompts and new_campaign calls."""
    r = {"welcome": 0, "choice": None, "settings": [], "asked": [], "answer": True, "new": 0}

    def fake_choice(master):
        r["welcome"] += 1
        return r["choice"]

    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", fake_choice)
    monkeypatch.setattr(
        app, "open_settings", lambda initial_provider=None: r["settings"].append(initial_provider)
    )

    def fake_ask(title, msg, **k):
        r["asked"].append(title)
        return r["answer"]

    monkeypatch.setattr("app.ui.app_window.messagebox.askyesno", fake_ask)

    def fake_new():
        r["new"] += 1

    monkeypatch.setattr(app.home_tab, "new_campaign", fake_new)
    return r


def test_fresh_config_shows_welcome_once(app, rec):
    app._run_startup_prompts()
    app._run_startup_prompts()  # e.g. the theme-change rebuild
    assert rec["welcome"] == 1
    assert config.load_config()["setup_welcome_shown"] is True


@pytest.mark.parametrize("choice, provider", [("cloud", "anthropic"), ("local", "ollama")])
def test_choice_opens_settings_then_offers_first_campaign(app, rec, choice, provider):
    rec["choice"] = choice
    app._run_startup_prompts()
    assert rec["settings"] == [provider]
    assert rec["asked"] == ["Create your first campaign?"]
    assert rec["new"] == 1
    assert app.notebook.select() == str(app.home_tab)


def test_declining_first_campaign_creates_nothing(app, rec):
    rec["choice"] = "cloud"
    rec["answer"] = False
    app._run_startup_prompts()
    assert rec["new"] == 0


def test_later_opens_nothing(app, rec):
    rec["choice"] = None
    app._run_startup_prompts()
    assert rec["welcome"] == 1
    assert rec["settings"] == []
    assert rec["asked"] == []


def test_existing_campaign_skips_offer(app, rec):
    library.create_campaign("Strahd")
    rec["choice"] = "cloud"
    app._run_startup_prompts()
    assert rec["settings"] == ["anthropic"]
    assert rec["asked"] == []


def test_ready_provider_shows_no_welcome(app, rec):
    config.save_provider_key("anthropic", "sk-test")
    app._run_startup_prompts()
    assert rec["welcome"] == 0


def test_library_import_failure_still_offers_welcome(app, rec, monkeypatch):
    def boom():
        raise RuntimeError("import exploded")

    monkeypatch.setattr(app, "_maybe_offer_library_import", boom)
    app._run_startup_prompts()
    assert rec["welcome"] == 1


def test_main_window_closed_during_welcome_does_nothing_more(app, rec, monkeypatch):
    def close_then_choose(master):
        rec["welcome"] += 1
        master.destroy()
        return "cloud"

    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", close_then_choose)
    app._run_startup_prompts()  # must not raise
    assert rec["settings"] == []
    assert rec["asked"] == []


def test_startup_timer_targets_run_startup_prompts(app):
    assert app._migration_after_id is not None
    info = app.tk.call("after", "info", app._migration_after_id)
    assert "_run_startup_prompts" in str(info)
