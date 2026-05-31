"""Campaigns tab: manage the speakers library — campaigns + version history."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from app import config
from app.core import library
from app.ui.theme import BTN_ACCENT, BTN_DANGER, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3


class CampaignsTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self._slugs: list[str] = []  # parallel to the campaign listbox rows
        self._selected_slug: str | None = None

        pad = {"padx": S_3, "pady": S_2}
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Speaker Campaigns", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad
        )

        # ---- Left: campaign list ----
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsw", **pad)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(left, textvariable=self.search_var, width=28).pack(fill="x")
        ttk.Label(left, text="Campaign", style=LBL_DIM).pack(anchor="w", pady=(S_2, 0))
        self.list = tk.Listbox(left, width=30, height=18, exportselection=False)
        self.list.pack(fill="both", expand=True)
        self.list.bind("<<ListboxSelect>>", self._on_select)
        ttk.Button(left, text="New campaign…", style=BTN_GHOST, command=self._new).pack(
            fill="x", pady=(S_2, 0)
        )
        ttk.Button(left, text="Import existing .json…", style=BTN_GHOST, command=self._import).pack(
            fill="x", pady=(S_2, 0)
        )

        # ---- Right: detail ----
        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew", **pad)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self.title_var = tk.StringVar(value="Select a campaign")
        ttk.Label(right, textvariable=self.title_var, style=LBL_HEADER).grid(
            row=0, column=0, sticky="w"
        )
        self.summary_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.summary_var, style=LBL_DIM).grid(
            row=1, column=0, sticky="w", pady=(0, S_2)
        )

        cols = ("version", "created", "label")
        self.versions = ttk.Treeview(right, columns=cols, show="headings", height=12)
        for c, w in (("version", 80), ("created", 160), ("label", 220)):
            self.versions.heading(c, text=c.title())
            self.versions.column(c, width=w, anchor="w")
        self.versions.grid(row=2, column=0, sticky="nsew")

        actions = ttk.Frame(right)
        actions.grid(row=3, column=0, sticky="w", pady=(S_2, 0))
        ttk.Button(actions, text="Set current", style=BTN_ACCENT, command=self._set_current).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Export copy…", style=BTN_GHOST, command=self._export).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Edit in Build Profile", style=BTN_GHOST, command=self._edit).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Rename…", style=BTN_GHOST, command=self._rename).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(actions, text="Delete…", style=BTN_DANGER, command=self._delete).pack(
            side="left"
        )

        self._refresh_list()

    # ---------- data ----------
    def on_show(self):
        self._refresh_list()

    def _refresh_list(self):
        query = self.search_var.get().strip().lower()
        rows = library.list_campaigns()
        self._slugs = []
        self.list.delete(0, "end")
        for r in rows:
            if query and query not in r["display_name"].lower():
                continue
            self._slugs.append(r["slug"])
            self.list.insert("end", f"{r['display_name']}  ({r['version_count']}v)")
        if self._selected_slug in self._slugs:
            idx = self._slugs.index(self._selected_slug)
            self.list.selection_set(idx)
            self._show_detail(self._selected_slug)
        else:
            self._selected_slug = None
            self._clear_detail()

    def _on_select(self, _e=None):
        sel = self.list.curselection()
        if not sel:
            return
        self._selected_slug = self._slugs[sel[0]]
        self._show_detail(self._selected_slug)

    def _clear_detail(self):
        self.title_var.set("Select a campaign")
        self.summary_var.set("")
        self.versions.delete(*self.versions.get_children())

    def _show_detail(self, slug):
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        if row is None:
            self._clear_detail()
            return
        cur = row["current"]
        versions = library.list_versions(slug)
        self.title_var.set(row["display_name"])
        try:
            doc = library.get_current_doc(slug)
            n = len(doc.get("players", []))
            ctx = (doc.get("context") or "").strip()
            self.summary_var.set(
                f"{n} speakers · {len(versions)} versions" + (f" · {ctx[:60]}" if ctx else "")
            )
        except Exception:
            self.summary_var.set(f"{len(versions)} versions")
        self.versions.delete(*self.versions.get_children())
        total = len(versions)
        for i, v in enumerate(reversed(versions)):
            num = total - i
            mark = "  ← current" if v["file"] == cur else ""
            self.versions.insert(
                "",
                "end",
                iid=v["file"],
                values=(f"v{num}{mark}", v["created_at"], v.get("label") or ""),
            )

    def _selected_version_file(self):
        sel = self.versions.selection()
        return sel[0] if sel else None

    # ---------- actions ----------
    def _new(self):
        name = simpledialog.askstring("New campaign", "Campaign name:", parent=self)
        if not name or not name.strip():
            return
        self._selected_slug = library.create_campaign(name.strip())
        self._refresh_list()

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._selected_slug = library.import_file(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Import failed:\n{e}")
            return
        config.set_last_dir("json", path)
        self._refresh_list()

    def _set_current(self):
        if not self._selected_slug:
            return
        vf = self._selected_version_file()
        if not vf:
            messagebox.showinfo("CampaignScribe", "Select a version first.")
            return
        library.set_current(self._selected_slug, vf)
        self._refresh_list()

    def _export(self):
        if not self._selected_slug:
            return
        vf = self._selected_version_file()
        if not vf:
            row = next(
                (r for r in library.list_campaigns() if r["slug"] == self._selected_slug), None
            )
            vf = row["current"] if row else ""
        if not vf:
            messagebox.showinfo("CampaignScribe", "Nothing to export.")
            return
        dest = filedialog.asksaveasfilename(
            title="Export speakers.json as…",
            defaultextension=".json",
            initialfile="speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        try:
            library.export_version(self._selected_slug, vf, dest)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Export failed:\n{e}")
            return
        config.set_last_dir("json", dest)
        messagebox.showinfo("CampaignScribe", f"Exported to {dest}")

    def _edit(self):
        if not self._selected_slug:
            return
        bp = getattr(self.app, "build_profile_tab", None)
        if bp is not None and hasattr(bp, "load_campaign"):
            bp.load_campaign(self._selected_slug)
            try:
                self.app.notebook.select(bp)  # select by widget — no index math
            except Exception:
                pass
        else:
            messagebox.showinfo(
                "CampaignScribe", "Open the Build Profile tab to edit this campaign."
            )

    def _rename(self):
        if not self._selected_slug:
            return
        new = simpledialog.askstring("Rename campaign", "New name:", parent=self)
        if not new or not new.strip():
            return
        self._selected_slug = library.rename_campaign(self._selected_slug, new.strip())
        self._refresh_list()

    def _delete(self):
        if not self._selected_slug:
            return
        if not messagebox.askyesno(
            "Delete campaign", "Delete this campaign and all its versions? This cannot be undone."
        ):
            return
        try:
            library.delete_campaign(self._selected_slug)
        except OSError as e:
            messagebox.showerror("CampaignScribe", f"Delete failed:\n{e}")
            return
        self._selected_slug = None
        self._refresh_list()
