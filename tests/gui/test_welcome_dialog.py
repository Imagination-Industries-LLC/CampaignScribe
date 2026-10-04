"""WelcomeDialog records the user's choice and closes."""

from __future__ import annotations

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


def _dlg(root):
    from app.ui.welcome_dialog import WelcomeDialog

    d = WelcomeDialog(root)
    d.update_idletasks()
    return d


@pytest.mark.parametrize(
    "button, expected", [("cloud_btn", "cloud"), ("local_btn", "local"), ("later_btn", None)]
)
def test_buttons_set_choice_and_close(root, button, expected):
    d = _dlg(root)
    getattr(d, button).invoke()
    assert d.choice == expected
    assert not d.winfo_exists()


def test_copy_matches_spec(root):
    from app.ui import welcome_dialog as w

    d = _dlg(root)
    try:
        assert d.title() == "Welcome to CampaignScribe"
        assert d.cloud_btn.cget("text") == "Use a cloud AI"
        assert d.local_btn.cget("text") == "Use a free local model"
        assert d.later_btn.cget("text") == "Later"
        assert w.CLOUD_CAPTION == "Claude, Google Gemini or OpenRouter — needs an API key"
        assert w.LOCAL_CAPTION == "Ollama or LM Studio, runs on your PC"
        assert w.BODY == (
            "CampaignScribe transcribes your sessions on this PC. To name speakers and write "
            "summaries it needs an AI model — pick one to set up now. "
            "You can change it any time in Settings (⚙)."
        )
    finally:
        d.destroy()


def test_escape_and_close_box_mean_later(root):
    d = _dlg(root)
    assert d.bind("<Escape>")  # binding exists
    d._choose(None)  # what both Escape and WM_DELETE_WINDOW call
    assert d.choice is None
    assert not d.winfo_exists()
