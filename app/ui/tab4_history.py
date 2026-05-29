"""Tab 6 — Session History: browse, rename, open files, delete records."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.data import db
from app.ui.common import open_path_native
from app.ui.theme import LBL_HEADER

STATUS_ICON = {
    "new": "🆕",
    "onboarded": "🔄",
    "transcribed": "📝",
    "summarized": "✅",
}


class Tab4History(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.selected_id: int | None = None

        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Session History", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(self, text="Search:").grid(row=1, column=0, sticky="w", **pad)
        self.search_var = tk.StringVar()
        ent = ttk.Entry(self, textvariable=self.search_var, width=40)
        ent.grid(row=1, column=1, sticky="w", **pad)
        ent.bind("<Return>", lambda _e: self.refresh())
        ttk.Button(self, text="Refresh", command=self.refresh).grid(
            row=1, column=2, sticky="w", **pad
        )

        cols = ("id", "name", "campaign", "created", "status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        headings = {
            "id": "ID",
            "name": "Session Name",
            "campaign": "Campaign",
            "created": "Created",
            "status": "Status",
        }
        widths = {"id": 50, "name": 280, "campaign": 200, "created": 140, "status": 120}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.grid(row=2, column=0, columnspan=4, sticky="nsew", **pad)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        det = ttk.LabelFrame(self, text="Details")
        det.grid(row=3, column=0, columnspan=4, sticky="ew", **pad)
        det.columnconfigure(1, weight=1)

        ttk.Label(det, text="Name:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(det, textvariable=self.name_var, width=50).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(det, text="Rename", command=self._rename).grid(row=0, column=2, padx=4)

        ttk.Label(det, text="Campaign:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        self.campaign_var = tk.StringVar()
        ttk.Entry(det, textvariable=self.campaign_var, width=50).grid(
            row=1, column=1, sticky="ew", padx=4
        )

        ttk.Label(det, text="Status:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        self.status_var = tk.StringVar()
        ttk.Label(det, textvariable=self.status_var).grid(row=2, column=1, sticky="w", padx=4)

        ttk.Label(det, text="speakers.json:").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        self.spk_var = tk.StringVar()
        ttk.Entry(det, textvariable=self.spk_var, width=60, state="readonly").grid(
            row=3, column=1, sticky="ew", padx=4
        )
        ttk.Button(det, text="Open", command=lambda: open_path_native(self.spk_var.get())).grid(
            row=3, column=2, padx=4
        )

        ttk.Label(det, text="Transcripts:").grid(row=4, column=0, sticky="w", padx=4, pady=2)
        self.tr_var = tk.StringVar()
        ttk.Entry(det, textvariable=self.tr_var, width=60, state="readonly").grid(
            row=4, column=1, sticky="ew", padx=4
        )
        ttk.Button(
            det, text="Open Folder", command=lambda: open_path_native(self.tr_var.get())
        ).grid(row=4, column=2, padx=4)

        ttk.Label(det, text="Summary:").grid(row=5, column=0, sticky="w", padx=4, pady=2)
        self.sum_var = tk.StringVar()
        ttk.Entry(det, textvariable=self.sum_var, width=60, state="readonly").grid(
            row=5, column=1, sticky="ew", padx=4
        )
        ttk.Button(det, text="Open", command=lambda: open_path_native(self.sum_var.get())).grid(
            row=5, column=2, padx=4
        )

        reopen = ttk.Frame(det)
        reopen.grid(row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 2))
        ttk.Button(reopen, text="Reopen in Transcribe", command=self._reopen_transcribe).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(reopen, text="Reopen in Summarize", command=self._reopen_summarize).pack(
            side="left", padx=6
        )

        ttk.Button(
            self, text="Delete Session Record (files NOT deleted)", command=self._delete
        ).grid(row=4, column=0, columnspan=4, sticky="e", **pad)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        self.refresh()

    def on_settings_changed(self):
        pass

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for s in db.list_sessions(self.search_var.get()):
            icon = STATUS_ICON.get(s.get("status", "new"), "")
            created = (s.get("created_at") or "")[:16]
            self.tree.insert(
                "",
                "end",
                iid=str(s["id"]),
                values=(
                    s["id"],
                    s["display_name"],
                    s.get("campaign_name") or "",
                    created,
                    f"{icon} {s.get('status', '?')}",
                ),
            )

    def _on_select(self):
        sel = self.tree.selection()
        if not sel:
            return
        sid = int(sel[0])
        self.selected_id = sid
        s = db.get_session(sid) or {}
        self.name_var.set(s.get("display_name", ""))
        self.campaign_var.set(s.get("campaign_name") or "")
        self.status_var.set(s.get("status", ""))
        self.spk_var.set(s.get("speakers_json_path") or "")
        self.tr_var.set(s.get("transcripts_folder") or "")
        self.sum_var.set(s.get("summary_path") or "")

    def _reopen_transcribe(self):
        if not self.selected_id:
            messagebox.showinfo("CampaignScribe", "Select a session first.")
            return
        self.app.tab5.load_session(self.selected_id)
        self.app.jump_to_tab(2)

    def _reopen_summarize(self):
        if not self.selected_id:
            messagebox.showinfo("CampaignScribe", "Select a session first.")
            return
        self.app.tab6.load_session(self.selected_id)
        self.app.jump_to_tab(3)

    def _rename(self):
        if not self.selected_id:
            return
        new_name = self.name_var.get().strip()
        if not new_name:
            return
        db.update_session(
            self.selected_id,
            display_name=new_name,
            campaign_name=self.campaign_var.get().strip(),
        )
        self.refresh()
        # Reselect
        try:
            self.tree.selection_set(str(self.selected_id))
        except tk.TclError:
            pass

    def _delete(self):
        if not self.selected_id:
            return
        if not messagebox.askyesno(
            "Delete session",
            "Remove this session record from the database?\n\nFiles on disk will NOT be deleted.",
        ):
            return
        db.delete_session(self.selected_id)
        self.selected_id = None
        for v in (
            self.name_var,
            self.campaign_var,
            self.status_var,
            self.spk_var,
            self.tr_var,
            self.sum_var,
        ):
            v.set("")
        self.refresh()
