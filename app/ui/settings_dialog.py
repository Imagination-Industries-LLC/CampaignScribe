"""Settings dialog: API key, HF token, default model, output folder, # speakers."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config


class SettingsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("CampaignScribe — Settings")
        self.transient(master)
        self.resizable(False, False)
        self.grab_set()

        cfg = config.load_config()

        pad = {"padx": 10, "pady": 6}
        row = 0

        ttk.Label(self, text="Anthropic API key:").grid(row=row, column=0, sticky="w", **pad)
        self.api_var = tk.StringVar(value=config.get_anthropic_key())
        self.api_entry = ttk.Entry(self, textvariable=self.api_var, width=55, show="•")
        self.api_entry.grid(row=row, column=1, **pad)
        self.api_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, text="Show", variable=self.api_show_var,
            command=self._toggle_api_visibility,
        ).grid(row=row, column=2, sticky="w", **pad)
        row += 1

        ttk.Label(self, text="HuggingFace token:").grid(row=row, column=0, sticky="w", **pad)
        self.hf_var = tk.StringVar(value=config.get_huggingface_token())
        self.hf_entry = ttk.Entry(self, textvariable=self.hf_var, width=55, show="•")
        self.hf_entry.grid(row=row, column=1, **pad)
        self.hf_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, text="Show", variable=self.hf_show_var,
            command=self._toggle_hf_visibility,
        ).grid(row=row, column=2, sticky="w", **pad)
        row += 1

        ttk.Label(self, text="Default output folder:").grid(row=row, column=0, sticky="w", **pad)
        self.out_var = tk.StringVar(value=cfg.get("default_output_folder", ""))
        ttk.Entry(self, textvariable=self.out_var, width=55).grid(row=row, column=1, **pad)
        ttk.Button(self, text="Browse…", command=self._browse_out).grid(row=row, column=2, **pad)
        row += 1

        ttk.Label(self, text="Default Whisper model:").grid(row=row, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(value=cfg.get("default_whisper_model", "large-v3"))
        ttk.Combobox(
            self, textvariable=self.model_var, state="readonly", width=20,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self, text="Default # speakers:").grid(row=row, column=0, sticky="w", **pad)
        self.spk_var = tk.IntVar(value=int(cfg.get("default_num_speakers", 5)))
        ttk.Spinbox(
            self, from_=1, to=20, textvariable=self.spk_var, width=8,
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=12)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.api_entry.focus_set()

    def _toggle_api_visibility(self):
        self.api_entry.config(show="" if self.api_show_var.get() else "•")

    def _toggle_hf_visibility(self):
        self.hf_entry.config(show="" if self.hf_show_var.get() else "•")

    def _browse_out(self):
        path = filedialog.askdirectory(
            title="Choose default output folder",
            initialdir=config.load_config().get("last_output_folder", "") or None,
        )
        if path:
            self.out_var.set(path)

    def _save(self):
        try:
            config.save_anthropic_key(self.api_var.get().strip())
            config.save_huggingface_token(self.hf_var.get().strip())
            cfg = config.load_config()
            cfg["default_output_folder"] = self.out_var.get().strip()
            cfg["default_whisper_model"] = self.model_var.get()
            cfg["default_num_speakers"] = int(self.spk_var.get() or 5)
            config.save_config(cfg)
        except Exception as e:
            messagebox.showerror("Settings", f"Could not save settings:\n{e}", parent=self)
            return
        self.destroy()
