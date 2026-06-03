"""SettingsDialog: discovery model + sample-minutes controls round-trip to config."""

from __future__ import annotations

import tkinter as tk

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


def test_settings_dialog_persists_discover_model(root):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root)
    root.update_idletasks()
    try:
        # Change the discovery model widget value and call _save directly.
        dlg.discover_model_var.set("medium")
        dlg._save()
    except tk.TclError:
        # destroy() inside _save is fine; dialog is gone but config was saved.
        pass

    assert config.load_config()["discover_whisper_model"] == "medium"


def test_settings_dialog_persists_discover_sample_minutes(root):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root)
    root.update_idletasks()
    try:
        dlg.discover_sample_var.set(15)
        dlg._save()
    except tk.TclError:
        pass

    assert config.load_config()["discover_sample_minutes"] == 15


def test_settings_dialog_initialises_from_saved_config(root):
    """Dialog reads previously saved discovery values on open."""
    cfg = config.load_config()
    cfg["discover_whisper_model"] = "base"
    cfg["discover_sample_minutes"] = 10
    config.save_config(cfg)

    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root)
    root.update_idletasks()
    try:
        assert dlg.discover_model_var.get() == "base"
        assert dlg.discover_sample_var.get() == 10
    finally:
        try:
            dlg.destroy()
        except tk.TclError:
            pass
