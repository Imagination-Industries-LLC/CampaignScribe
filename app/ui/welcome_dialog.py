"""First-launch welcome: choose a cloud or local AI provider, or skip for now."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, LBL_TITLE

TITLE = "Welcome to CampaignScribe"
BODY = (
    "CampaignScribe transcribes your sessions on this PC. To name speakers and write "
    "summaries it needs an AI model — pick one to set up now. You can change it any "
    "time in Settings (⚙)."
)
CLOUD_CAPTION = "Claude, Google Gemini or OpenRouter — needs an API key"
LOCAL_CAPTION = "Ollama or LM Studio, runs on your PC"


class WelcomeDialog(tk.Toplevel):
    """Modal welcome. ``choice`` is "cloud", "local" or None once it closes."""

    def __init__(self, master):
        super().__init__(master)
        self.choice: str | None = None
        self.title(TITLE)
        self.transient(master)
        self.resizable(False, False)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=TITLE, style=LBL_TITLE).pack(anchor="w")
        ttk.Label(body, text=BODY, wraplength=440, justify="left").pack(anchor="w", pady=(8, 16))

        self.cloud_btn = ttk.Button(
            body, text="Use a cloud AI", style=BTN_ACCENT, command=lambda: self._choose("cloud")
        )
        self.cloud_btn.pack(fill="x")
        ttk.Label(body, text=CLOUD_CAPTION, style=LBL_DIM).pack(anchor="w", pady=(2, 12))

        self.local_btn = ttk.Button(
            body,
            text="Use a free local model",
            style=BTN_ACCENT,
            command=lambda: self._choose("local"),
        )
        self.local_btn.pack(fill="x")
        ttk.Label(body, text=LOCAL_CAPTION, style=LBL_DIM).pack(anchor="w", pady=(2, 16))

        self.later_btn = ttk.Button(
            body, text="Later", style=BTN_GHOST, command=lambda: self._choose(None)
        )
        self.later_btn.pack(anchor="e")

        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(None))
        self.bind("<Escape>", lambda _e: self._choose(None))
        self.grab_set()
        self.cloud_btn.focus_set()

    def _choose(self, choice: str | None) -> None:
        self.choice = choice
        self.destroy()


def ask_setup_choice(master) -> str | None:
    """Show the welcome modally and return "cloud", "local" or None."""
    dlg = WelcomeDialog(master)
    master.wait_window(dlg)
    return dlg.choice
