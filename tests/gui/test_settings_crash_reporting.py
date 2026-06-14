import tkinter as tk

import pytest

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


def test_crash_checkbox_defaults_off_and_saves(root, monkeypatch):
    from app import config
    from app.core import crash_reporting
    from app.ui import settings_dialog

    toggled = []
    monkeypatch.setattr(crash_reporting, "set_enabled", lambda v: toggled.append(v))

    dlg = settings_dialog.SettingsDialog(root)
    try:
        assert dlg.crash_var.get() is False
        dlg.crash_var.set(True)
        dlg._save()
        assert config.load_config().get("crash_reporting_enabled") is True
        assert toggled[-1] is True
    finally:
        try:
            dlg.destroy()
        except tk.TclError:
            pass
