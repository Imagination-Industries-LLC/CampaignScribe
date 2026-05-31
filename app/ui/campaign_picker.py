"""Reusable 'Campaign' picker that yields a speakers.json file PATH — either a
library campaign's current-version file or a loose file the user browses ('Use a
file instead…'). Downstream code loads by path, unchanged."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import library, speakers_io
from app.ui.theme import BTN_GHOST, S_2, S_3


class CampaignPicker(ttk.Frame):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self._on_change = on_change
        self._file_path: str | None = None  # set when using a loose file
        self._slug_by_label: dict[str, str] = {}

        ttk.Label(self, text="Campaign:").grid(row=0, column=0, sticky="w", padx=(0, S_2))
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.var, state="readonly", width=34)
        self.combo.grid(row=0, column=1, sticky="ew", padx=S_2)
        self.combo.bind("<<ComboboxSelected>>", self._on_combo)
        ttk.Button(
            self, text="Use a file instead…", style=BTN_GHOST, command=self._browse_file
        ).grid(row=0, column=2, padx=(S_3, 0))
        self.columnconfigure(1, weight=1)
        self.refresh()

    def refresh(self) -> None:
        rows = library.list_campaigns()
        self._slug_by_label = {}
        labels = []
        for r in rows:
            label = f"{r['display_name']} ({r['version_count']}v)"
            self._slug_by_label[label] = r["slug"]
            labels.append(label)
        self.combo["values"] = labels
        if self.var.get() not in labels:
            last = config.load_config().get("last_campaign", "")
            match = next((lbl for lbl, slug in self._slug_by_label.items() if slug == last), None)
            self.var.set(match or (labels[0] if labels else ""))
        self._file_path = None

    def _on_combo(self, _e=None):
        self._file_path = None
        slug = self.selected_slug()
        if slug:
            cfg = config.load_config()
            cfg["last_campaign"] = slug
            config.save_config(cfg)
        if self._on_change:
            self._on_change()

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        config.set_last_dir("json", path)
        self._file_path = path
        self.var.set(f"(file) {path}")
        if self._on_change:
            self._on_change()

    def selected_slug(self) -> str | None:
        if self._file_path:
            return None
        return self._slug_by_label.get(self.var.get())

    def selected_path(self) -> str | None:
        """The speakers.json path to load (loose file, or the campaign's current version)."""
        if self._file_path:
            return self._file_path
        slug = self.selected_slug()
        if not slug:
            return None
        try:
            return str(library.current_version_path(slug))
        except FileNotFoundError:
            return None  # campaign has no versions yet

    def select_by_slug(self, slug: str) -> bool:
        """Select the given campaign by slug (refreshing if needed). Fires on_change.
        Returns True if the campaign was found and selected."""
        label = next((lbl for lbl, s in self._slug_by_label.items() if s == slug), None)
        if label is None:
            self.refresh()
            label = next((lbl for lbl, s in self._slug_by_label.items() if s == slug), None)
        if label is None:
            return False
        self._file_path = None
        self.var.set(label)
        self._on_combo()  # persists last_campaign + fires on_change
        return True
