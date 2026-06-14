"""Help -> Feedback & Support hub dialog (Slice A: report / diagnostics / email / discussions)."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core import diagnostics, support
from app.ui.common import make_readonly, open_url
from app.ui.theme import BTN_GHOST, LBL_DIM, LBL_TITLE


class FeedbackSupportDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Feedback & Support — CampaignScribe")
        self.transient(master)
        self.geometry("560x520")
        self.minsize(480, 420)
        self.grab_set()

        pad = {"padx": 16, "pady": 6}
        ttk.Label(self, text="Feedback & Support", style=LBL_TITLE).pack(anchor="w", **pad)
        ttk.Label(
            self,
            text="Everything here is optional and only sent when you choose to.",
            style=LBL_DIM,
            wraplength=500,
        ).pack(anchor="w", padx=16)

        self._section(
            "🐞  Report a problem",
            "Opens a pre-filled GitHub issue with non-sensitive diagnostics.",
            "Report a problem",
            self._report_problem,
        )
        self._section(
            "📋  Copy diagnostics",
            "Preview and copy local diagnostics (version, GPU, recent errors).",
            "Copy diagnostics…",
            self._copy_diagnostics,
        )
        # Email feedback (custom: a copyable address as a fallback for users with no mail client).
        email_frame = ttk.Frame(self)
        email_frame.pack(fill="x", padx=16, pady=8)
        ttk.Label(email_frame, text="✉️  Email feedback").pack(anchor="w")
        ttk.Label(
            email_frame,
            text=f"Write to {support.FEEDBACK_EMAIL}. Opens a draft with a short build-info header.",
            style=LBL_DIM,
            wraplength=500,
        ).pack(anchor="w")
        email_btns = ttk.Frame(email_frame)
        email_btns.pack(anchor="w", pady=4)
        ttk.Button(email_btns, text="Email us", style=BTN_GHOST, command=self._email_feedback).pack(
            side="left"
        )
        ttk.Button(
            email_btns, text="Copy address", style=BTN_GHOST, command=self._copy_email_address
        ).pack(side="left", padx=6)
        self._section(
            "💡  Feature ideas",
            "Discuss ideas and see what's planned on GitHub Discussions.",
            "Open Discussions",
            self._open_discussions,
        )

        # Support development (Slice B): a button per configured funding platform.
        self._support_buttons: dict = {}
        links = support.funding_links()
        if links:
            sup = ttk.Frame(self)
            sup.pack(fill="x", padx=16, pady=8)
            ttk.Label(sup, text="❤️  Support development").pack(anchor="w")
            ttk.Label(
                sup,
                text=(
                    "CampaignScribe is free and open. Donations support ongoing development "
                    "only — they do not cover AI model or API costs (you pay your AI provider "
                    "directly; local and other low-cost model options are on the roadmap)."
                ),
                style=LBL_DIM,
                wraplength=500,
            ).pack(anchor="w")
            sup_btns = ttk.Frame(sup)
            sup_btns.pack(anchor="w", pady=4)
            for label, url in links:
                btn = ttk.Button(
                    sup_btns, text=label, style=BTN_GHOST, command=lambda u=url: open_url(u)
                )
                btn.pack(side="left", padx=(0, 6))
                self._support_buttons[label] = btn

        ttk.Button(self, text="Close", style=BTN_GHOST, command=self.destroy).pack(pady=12)

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _section(self, title: str, desc: str, btn_text: str, command) -> None:
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=16, pady=8)
        ttk.Label(frame, text=title).pack(anchor="w")
        ttk.Label(frame, text=desc, style=LBL_DIM, wraplength=500).pack(anchor="w")
        ttk.Button(frame, text=btn_text, style=BTN_GHOST, command=command).pack(anchor="w", pady=4)

    # ---- actions ----
    def _report_problem(self) -> None:
        bundle = diagnostics.build_diagnostics_bundle(include_log_tail=True)
        body = (
            "**Steps to reproduce:**\n1. \n2. \n\n"
            "**Expected:**\n\n**Actual:**\n\n"
            "**Diagnostics:**\n```\n" + bundle + "\n```\n"
        )
        url = support.new_issue_url("Bug report", body)
        if support.issue_url_too_long(url):
            self.clipboard_clear()
            self.clipboard_append(bundle)
            body = (
                "**Steps to reproduce:**\n1. \n2. \n\n**Expected:**\n\n**Actual:**\n\n"
                "**Diagnostics:** (paste from your clipboard here)\n"
            )
            url = support.new_issue_url("Bug report", body)
            messagebox.showinfo(
                "Report a problem",
                "Your diagnostics were copied to the clipboard — paste them into the issue.",
                parent=self,
            )
        open_url(url)

    def _copy_diagnostics(self) -> None:
        bundle = diagnostics.build_diagnostics_bundle(include_log_tail=True)
        preview = tk.Toplevel(self)
        preview.title("Diagnostics preview")
        preview.transient(self)
        preview.grab_set()
        preview.geometry("620x460")
        ttk.Label(
            preview,
            text="This is exactly what will be shared. Nothing is sent automatically.",
            style=LBL_DIM,
            wraplength=580,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        txt = tk.Text(preview, wrap="word", height=18)
        txt.insert("1.0", bundle)
        make_readonly(txt)
        txt.pack(fill="both", expand=True, padx=12, pady=4)
        row = ttk.Frame(preview)
        row.pack(fill="x", padx=12, pady=8)

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(bundle)
            messagebox.showinfo("Copy diagnostics", "Copied to clipboard.", parent=preview)

        def _save():
            path = filedialog.asksaveasfilename(
                parent=preview,
                defaultextension=".txt",
                filetypes=[("Text file", "*.txt")],
                initialfile="campaignscribe-diagnostics.txt",
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(bundle)
            except OSError as e:
                messagebox.showerror("Save failed", f"Could not save: {e}", parent=preview)

        def _close():
            preview.destroy()
            self.grab_set()  # restore the parent dialog's modal grab

        ttk.Button(row, text="Copy to clipboard", style=BTN_GHOST, command=_copy).pack(side="left")
        ttk.Button(row, text="Save as .txt…", style=BTN_GHOST, command=_save).pack(
            side="left", padx=6
        )
        ttk.Button(row, text="Close", style=BTN_GHOST, command=_close).pack(side="right")
        preview.protocol("WM_DELETE_WINDOW", _close)

    def _email_feedback(self) -> None:
        from app import __version__

        subject = f"CampaignScribe Feedback (v{__version__})"
        body = diagnostics.build_email_header() + "\n\n— your feedback below —\n"
        open_url(support.mailto_url(subject, body))

    def _copy_email_address(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(support.FEEDBACK_EMAIL)
        messagebox.showinfo(
            "Email feedback", f"Copied {support.FEEDBACK_EMAIL} to the clipboard.", parent=self
        )

    def _open_discussions(self) -> None:
        open_url(support.discussions_url())


def show_support_nudge(master) -> None:
    """The gentle one-time support nudge dialog (Support / Maybe later / Don't show again).
    The 'shown' flag is set by support.record_summary_and_check_nudge before this is called,
    so every close path means it never appears again."""
    win = tk.Toplevel(master)
    win.title("Support CampaignScribe")
    win.transient(master)
    win.grab_set()
    ttk.Label(win, text="Enjoying CampaignScribe?", style=LBL_TITLE).pack(padx=20, pady=(16, 6))
    ttk.Label(
        win,
        text=(
            "It's free and open. If it's saved you time at the table, a one-time $5/$10 helps "
            "development. (This doesn't cover AI costs.)"
        ),
        wraplength=360,
        justify="center",
        style=LBL_DIM,
    ).pack(padx=20)
    row = ttk.Frame(win)
    row.pack(pady=14)

    def _support():
        win.destroy()
        FeedbackSupportDialog(master)

    ttk.Button(row, text="Support", style=BTN_GHOST, command=_support).pack(side="left", padx=4)
    ttk.Button(row, text="Maybe later", style=BTN_GHOST, command=win.destroy).pack(
        side="left", padx=4
    )
    ttk.Button(row, text="Don't show again", style=BTN_GHOST, command=win.destroy).pack(
        side="left", padx=4
    )
    win.bind("<Escape>", lambda _e: win.destroy())
    win.focus_set()
    win.update_idletasks()


def maybe_show_support_nudge(master) -> bool:
    """Show the support nudge if it is due now. Returns whether it was shown. Best-effort."""
    if not support.record_summary_and_check_nudge():
        return False
    show_support_nudge(master)
    return True
