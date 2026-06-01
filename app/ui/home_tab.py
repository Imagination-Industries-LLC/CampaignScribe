"""Home: the campaign + session hub. Merges Campaigns and History."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from app import config
from app.core import library
from app.data import db
from app.ui.theme import BTN_ACCENT, BTN_DANGER, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3

STATUS_CHIP = {
    "new": "🆕 recorded",
    "onboarded": "🔄 onboarded",
    "transcribed": "📝 transcribed",
    "summarized": "✅ summarized",
}

UNCATEGORIZED_LABEL = "▣ Uncategorized (loose sessions)"


class HomeTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self._rows: list[str | None] = []  # parallel to campaign_list; None = Uncategorized
        self.selected_slug: str | None = None
        self.selected_is_uncat = False
        self.selected_session_id: int | None = None

        pad = {"padx": S_3, "pady": S_2}
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Campaign Home", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad
        )

        # ---- Left: campaigns ----
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsw", **pad)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_campaigns())
        ttk.Entry(left, textvariable=self.search_var, width=28).pack(fill="x")
        ttk.Label(left, text="Campaign", style=LBL_DIM).pack(anchor="w", pady=(S_2, 0))
        self.campaign_list = tk.Listbox(left, width=30, height=18, exportselection=False)
        self.campaign_list.pack(fill="both", expand=True)
        self.campaign_list.bind("<<ListboxSelect>>", self._on_campaign_select)
        ttk.Button(left, text="＋ New campaign…", style=BTN_GHOST, command=self._new_campaign).pack(
            fill="x", pady=(S_2, 0)
        )
        ttk.Button(left, text="Import existing .json…", style=BTN_GHOST, command=self._import).pack(
            fill="x", pady=(S_2, 0)
        )

        # ---- Right: detail ----
        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew", **pad)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self.title_var = tk.StringVar(value="Select a campaign")
        ttk.Label(right, textvariable=self.title_var, style=LBL_HEADER).grid(
            row=0, column=0, sticky="w"
        )
        roster_row = ttk.Frame(right)
        roster_row.grid(row=1, column=0, sticky="ew", pady=(0, S_2))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(roster_row, textvariable=self.summary_var, style=LBL_DIM).pack(side="left")
        self.edit_btn = ttk.Button(
            roster_row, text="Edit profile ▸", style=BTN_GHOST, command=self._edit_profile
        )
        self.edit_btn.pack(side="right")

        self.new_session_btn = ttk.Button(
            right, text="＋ New session", style=BTN_ACCENT, command=self._new_session
        )
        self.new_session_btn.grid(row=2, column=0, sticky="w", pady=(0, S_2))
        self.new_session_btn.state(["disabled"])

        cols = ("id", "name", "created", "status")
        self.session_tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        for c, head, w in (
            ("id", "ID", 50),
            ("name", "Session", 280),
            ("created", "Created", 140),
            ("status", "Status", 150),
        ):
            self.session_tree.heading(c, text=head)
            self.session_tree.column(c, width=w, anchor="w")
        self.session_tree.grid(row=3, column=0, sticky="nsew")
        self.session_tree.bind("<<TreeviewSelect>>", self._on_session_select)
        self.session_tree.bind("<Double-Button-1>", lambda _e: self._open_selected_session())

        actions = ttk.Frame(right)
        actions.grid(row=4, column=0, sticky="w", pady=(S_2, 0))
        ttk.Button(actions, text="Open", style=BTN_GHOST, command=self._open_selected_session).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Rename…", style=BTN_GHOST, command=self._rename_session).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(
            actions, text="Delete record…", style=BTN_DANGER, command=self._delete_session
        ).pack(side="left")

        self._refresh_campaigns()

    # ---------- lifecycle ----------
    def on_settings_changed(self):
        pass

    def on_show(self):
        self._refresh_campaigns()

    # ---------- campaigns ----------
    def _refresh_campaigns(self):
        query = self.search_var.get().strip().lower()
        rows = library.list_campaigns()
        self._rows = []
        self.campaign_list.delete(0, "end")
        for r in rows:
            if query and query not in r["display_name"].lower():
                continue
            self._rows.append(r["slug"])
            self.campaign_list.insert("end", f"{r['display_name']}  ({r['version_count']}v)")
        self._rows.append(None)  # Uncategorized bucket always last
        self.campaign_list.insert("end", UNCATEGORIZED_LABEL)
        if self.selected_is_uncat:
            self.select_uncategorized()
            idx = len(self._rows) - 1  # Uncategorized is always last
            self.campaign_list.selection_set(idx)
            self.campaign_list.see(idx)
        elif self.selected_slug in self._rows:
            self.select_campaign(self.selected_slug)
            idx = self._rows.index(self.selected_slug)
            self.campaign_list.selection_set(idx)
            self.campaign_list.see(idx)
        else:
            self._clear_detail()

    def _on_campaign_select(self, _e=None):
        sel = self.campaign_list.curselection()
        if not sel:
            return
        target = self._rows[sel[0]]
        if target is None:
            self.select_uncategorized()
        else:
            self.select_campaign(target)

    def select_campaign(self, slug: str):
        self.selected_slug = slug
        self.selected_is_uncat = False
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        if row is None:
            self._clear_detail()
            return
        self.title_var.set(row["display_name"])
        try:
            doc = library.get_current_doc(slug)
            players = doc.get("players", [])
            dms = sum(1 for p in players if "dungeon master" in (p.get("role", "").lower()))
            self.summary_var.set(
                f"v{row['version_count']} · {len(players) - dms} players · {dms} DM · "
                f"{len(doc.get('npcs', []))} NPCs"
            )
        except Exception:
            self.summary_var.set(f"v{row['version_count']} · no profile yet")
        self.edit_btn.state(["!disabled"])
        self.new_session_btn.state(["!disabled"])
        self._refresh_sessions(db.list_sessions(campaign_slug=slug))

    def select_uncategorized(self):
        self.selected_slug = None
        self.selected_is_uncat = True
        self.title_var.set("Uncategorized")
        self.summary_var.set("Loose sessions not filed into a campaign")
        self.edit_btn.state(["disabled"])
        self.new_session_btn.state(["disabled"])
        self._refresh_sessions(db.list_sessions(campaign_slug=db.UNCATEGORIZED))

    def _clear_detail(self):
        self.selected_slug = None
        self.selected_is_uncat = False
        self.title_var.set("Select a campaign")
        self.summary_var.set("")
        self.session_tree.delete(*self.session_tree.get_children())
        self.edit_btn.state(["disabled"])
        self.new_session_btn.state(["disabled"])

    # ---------- sessions ----------
    def _refresh_sessions(self, sessions):
        self.session_tree.delete(*self.session_tree.get_children())
        for s in sessions:
            self.session_tree.insert(
                "",
                "end",
                iid=str(s["id"]),
                values=(
                    s["id"],
                    s["display_name"],
                    (s.get("created_at") or "")[:16],
                    STATUS_CHIP.get(s.get("status", "new"), s.get("status", "?")),
                ),
            )

    def _on_session_select(self, _e=None):
        sel = self.session_tree.selection()
        self.selected_session_id = int(sel[0]) if sel else None

    def _new_session(self):
        if not self.selected_slug or self.selected_is_uncat:
            messagebox.showinfo("CampaignScribe", "Select a campaign first.")
            return None
        slug = self.selected_slug
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        name = row["display_name"] if row else ""
        sid = db.create_session("Untitled Session", campaign_name=name, campaign_slug=slug)
        self._refresh_sessions(db.list_sessions(campaign_slug=slug))
        self.app.open_session(sid)
        return sid

    def _open_selected_session(self):
        if self.selected_session_id is None:
            messagebox.showinfo("CampaignScribe", "Select a session first.")
            return
        self.app.open_session(self.selected_session_id)

    def _rename_session(self):
        if self.selected_session_id is None:
            return
        new = simpledialog.askstring("Rename session", "New name:", parent=self)
        if not new or not new.strip():
            return
        db.update_session(self.selected_session_id, display_name=new.strip())
        self._reload_current()

    def _delete_session(self, confirm: bool = True):
        if self.selected_session_id is None:
            return
        if confirm and not messagebox.askyesno(
            "Delete session record",
            "Remove this session record from the database?\n\nFiles on disk are NOT deleted.",
        ):
            return
        db.delete_session(self.selected_session_id)
        self.selected_session_id = None
        self._reload_current()

    def _reload_current(self):
        if self.selected_is_uncat:
            self.select_uncategorized()
        elif self.selected_slug:
            self.select_campaign(self.selected_slug)

    # ---------- campaign actions ----------
    def _edit_profile(self):
        if not self.selected_slug:
            messagebox.showinfo("CampaignScribe", "Select a campaign first.")
            return
        self.app.open_edit_profile(self.selected_slug)

    def _new_campaign(self):
        name = simpledialog.askstring("New campaign", "Campaign name:", parent=self)
        if not name or not name.strip():
            return
        self.selected_slug = library.create_campaign(name.strip())
        self.selected_is_uncat = False
        self._refresh_campaigns()

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.selected_slug = library.import_file(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Import failed:\n{e}")
            return
        config.set_last_dir("json", path)
        self.selected_is_uncat = False
        self._refresh_campaigns()
