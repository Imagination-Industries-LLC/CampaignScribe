"""Settings -> Discord recording section."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
from app.core import discord_recorder

pytestmark = pytest.mark.gui

TOKEN = "MTIzNDU2Nzg5MDEyMzQ1Njc4.x.y"  # base64url("123456789012345678")


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


def _dlg(root, **kw):
    from app.ui.settings_dialog import SettingsDialog

    return SettingsDialog(root, **kw)


def _inventory(timeout_s=20.0, token=None):
    return {
        "event": "inventory",
        "guilds": [{"id": "1", "name": "MDMT", "voice_channels": [{"id": "2", "name": "Table"}]}],
        "owner": {"id": "9", "name": "Mike"},
        "owner_voice": None,
        "application_id": "5",
    }


def test_discord_defaults(root):
    dlg = _dlg(root)
    dlg.update_idletasks()
    try:
        assert dlg.discord_token_var.get() == ""
        assert str(dlg.discord_invite_btn["state"]) == "disabled"
        assert dlg.discord_max_hours_var.get() == 6 and dlg.discord_max_minutes_var.get() == 0
        assert dlg.discord_notice_var.get().startswith("🔴 This voice channel is being recorded")
    finally:
        dlg.destroy()


def test_invite_enables_with_token_and_opens_url(root, monkeypatch):
    opened = []
    monkeypatch.setattr("app.ui.settings_dialog.open_url", lambda u: opened.append(u))
    dlg = _dlg(root)
    try:
        dlg.discord_token_var.set(TOKEN)
        dlg.update_idletasks()
        assert str(dlg.discord_invite_btn["state"]) == "normal"
        dlg.discord_invite_btn.invoke()
        assert "client_id=123456789012345678" in opened[0] and "permissions=1051648" in opened[0]
        dlg.discord_token_var.set("garbage")
        assert str(dlg.discord_invite_btn["state"]) == "disabled"
    finally:
        dlg.destroy()


def test_save_persists_token_notice_and_max(root):
    dlg = _dlg(root)
    dlg.discord_token_var.set("tok")
    dlg.discord_notice_var.set("Recording!")
    dlg.discord_max_hours_var.set(2)
    dlg.discord_max_minutes_var.set(30)
    dlg._save()
    assert config.get_discord_token() == "tok"
    cfg = config.load_config()
    assert cfg["discord_notice"] == "Recording!" and cfg["discord_max_minutes"] == 150


def test_save_rejects_zero_max(root, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "app.ui.settings_dialog.messagebox.showerror", lambda t, m, **k: errors.append(m)
    )
    dlg = _dlg(root)
    try:
        dlg.discord_token_var.set("tok")
        dlg.discord_max_hours_var.set(0)
        dlg.discord_max_minutes_var.set(0)
        dlg._save()
        assert errors == ["Max recording length must be at least 1 minute."]
        assert config.load_config()["discord_max_minutes"] == 360
        assert config.get_discord_token() == ""
        assert dlg.winfo_exists()
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_focus_max_length(root, monkeypatch):
    # OS foreground is not reliable on a withdrawn master / CI, so record the focus request.
    calls = []
    monkeypatch.setattr(tk.Misc, "focus_force", lambda self: calls.append(self), raising=True)
    dlg = _dlg(root, focus="discord_max_length")
    dlg.update()
    try:
        assert dlg.discord_max_hours_spin in calls
    finally:
        dlg.destroy()


def test_connection_test_reports_inventory(root, monkeypatch):
    seen = []

    def fake(timeout_s=20.0, token=None):
        seen.append(token)
        return _inventory()

    monkeypatch.setattr("app.core.discord_recorder.list_inventory", fake)
    dlg = _dlg(root)
    try:
        dlg.discord_token_var.set("tok")
        dlg._test_discord(_sync=True)
        assert dlg.discord_test_label.cget("text").startswith("✓ Connected — 1 server")
        assert seen == ["tok"]
    finally:
        dlg.destroy()


def test_connection_test_shows_recorder_error(root, monkeypatch):
    def boom(timeout_s=20.0, token=None):
        raise discord_recorder.RecorderError("bad_token", "Discord rejected the token.")

    monkeypatch.setattr("app.core.discord_recorder.list_inventory", boom)
    dlg = _dlg(root)
    try:
        dlg.discord_token_var.set("tok")
        dlg._test_discord(_sync=True)
        assert dlg.discord_test_label.cget("text") == "✗ Discord rejected the token."
    finally:
        dlg.destroy()


def test_setup_guide_opens(root):
    dlg = _dlg(root)
    before = set(dlg.winfo_children())
    try:
        dlg._show_discord_guide()
        new = [w for w in dlg.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
        assert len(new) == 1
        guide = new[0]
        texts = []

        def walk(w):
            if isinstance(w, tk.Text):
                texts.append(w.get("1.0", "end"))
            for c in w.winfo_children():
                walk(c)

        walk(guide)
        body = "\n".join(texts)
        assert "Public Bot" in body and "Reset Token" in body
        assert "Privileged" in body
        guide.destroy()
    finally:
        dlg.destroy()


def test_connection_test_shows_unavailable_message(root, monkeypatch):
    msg = "The Discord recorder components are missing. Reinstall CampaignScribe."

    def boom(timeout_s=20.0, token=None):
        raise discord_recorder.RecorderUnavailable(msg)

    monkeypatch.setattr("app.core.discord_recorder.list_inventory", boom)
    dlg = _dlg(root)
    try:
        dlg.discord_token_var.set("tok")
        dlg._test_discord(_sync=True)
        assert dlg.discord_test_label.cget("text") == "\u2717 " + msg
    finally:
        dlg.destroy()


def test_dialog_fits_small_screen_and_save_is_reachable(root, monkeypatch):
    monkeypatch.setattr(tk.Misc, "winfo_screenheight", lambda self: 700)
    root.deiconify()  # geometry assertions need a mapped transient
    root.update()
    dlg = _dlg(root)
    try:
        dlg.update()
        height = int(dlg.geometry().split("+")[0].split("x")[1])
        assert height <= 700 - 96
        # scrolling is real: the content is taller than the viewport
        assert dlg._body.winfo_reqheight() > dlg._scroll.canvas.winfo_height()
        assert dlg.save_btn.winfo_ismapped()
        # Save sits inside the dialog's bounds, below the scroll area
        assert dlg.save_btn.winfo_rooty() + dlg.save_btn.winfo_height() <= (
            dlg.winfo_rooty() + dlg.winfo_height()
        )
    finally:
        dlg.destroy()


def test_focus_scrolls_hours_spinbox_into_view(root, monkeypatch):
    monkeypatch.setattr(tk.Misc, "winfo_screenheight", lambda self: 600)
    root.deiconify()
    root.update()
    monkeypatch.setattr(tk.Misc, "focus_force", lambda self: None, raising=True)
    dlg = _dlg(root, focus="discord_max_length")
    dlg.update()
    try:
        canvas = dlg._scroll.canvas
        assert canvas.yview()[0] > 0  # actually scrolled
        top = canvas.winfo_rooty()
        spin_y = dlg.discord_max_hours_spin.winfo_rooty()
        assert top <= spin_y <= top + canvas.winfo_height()
    finally:
        dlg.destroy()


def test_dialog_is_not_clipped_on_the_real_screen(root):
    root.deiconify()
    root.update()
    dlg = _dlg(root)
    try:
        dlg.update()
        width, height = (int(v) for v in dlg.geometry().split("+")[0].split("x"))
        assert width >= dlg._body.winfo_reqwidth()
        right = dlg.winfo_rootx() + dlg.winfo_width()
        btn = dlg.discord_invite_btn
        assert btn.winfo_rootx() + btn.winfo_width() <= right
        btn_h = dlg._btn_frame.winfo_reqheight() + 24
        expected = min(dlg._body.winfo_reqheight() + btn_h, dlg.winfo_screenheight() - 96)
        assert height == expected
    finally:
        dlg.destroy()
