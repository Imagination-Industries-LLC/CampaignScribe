"""Tab 4 — Summarization: per-part summaries plus optional consolidated session doc."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from app import config
from app.core import speakers_io, summarizer
from app.data import db
from app.prompts.default_prompt import DEFAULT_PROMPT_NAME, DEFAULT_SUMMARY_PROMPT
from app.ui.common import open_path_native, open_transcript_editor, reveal_in_folder
from app.ui.theme import BTN_ACCENT, LBL_DIM, LBL_HEADER


class PromptDialog(tk.Toplevel):
    def __init__(self, master, name: str = "", content: str = "", title: str = "Prompt"):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.grab_set()
        self.result: dict[str, str] | None = None

        ttk.Label(self, text="Name:").pack(anchor="w", padx=8, pady=4)
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(self, textvariable=self.name_var, width=60).pack(fill="x", padx=8)

        ttk.Label(self, text="Content:").pack(anchor="w", padx=8, pady=4)
        self.text = tk.Text(self, width=80, height=24, wrap="word")
        self.text.insert("1.0", content)
        self.text.pack(fill="both", expand=True, padx=8, pady=4)

        bf = ttk.Frame(self)
        bf.pack(fill="x", pady=6)
        ttk.Button(bf, text="Save", command=self._save).pack(side="right", padx=6)
        ttk.Button(bf, text="Cancel", command=self.destroy).pack(side="right")

    def _save(self):
        name = self.name_var.get().strip()
        body = self.text.get("1.0", "end").strip()
        if not name:
            messagebox.showerror("CampaignScribe", "Name is required.", parent=self)
            return
        if not body:
            messagebox.showerror("CampaignScribe", "Content is required.", parent=self)
            return
        self.result = {"name": name, "content": body}
        self.destroy()


class Tab6Summarize(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.transcript_files: list[str] = []
        self.speakers_path: str | None = None
        self.session_id: int | None = None
        self.part_summaries: list[str] = []
        self.consolidated_path: str | None = None
        self._busy = False
        self._cancel = threading.Event()

        cfg = config.load_config()

        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Summarization", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(self, text="speakers.json:").grid(row=1, column=0, sticky="w", **pad)
        self.speakers_var = tk.StringVar(value=cfg.get("last_speakers_json", ""))
        if self.speakers_var.get():
            self.speakers_path = self.speakers_var.get()
        ttk.Entry(self, textvariable=self.speakers_var, width=60, state="readonly").grid(
            row=1, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._browse_speakers).grid(
            row=1, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Session (optional):").grid(row=2, column=0, sticky="w", **pad)
        self.session_combo = ttk.Combobox(self, state="readonly", width=60)
        self.session_combo.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Button(self, text="Refresh", command=self.refresh_sessions).grid(
            row=2, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Transcript files:").grid(row=3, column=0, sticky="nw", **pad)
        self.files_box = tk.Listbox(self, height=4, selectmode="extended")
        self.files_box.grid(row=3, column=1, columnspan=2, sticky="nsew", **pad)
        bcol = ttk.Frame(self)
        bcol.grid(row=3, column=3, sticky="nw", **pad)
        ttk.Button(bcol, text="Add Files…", command=self._add_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Edit Selected", command=self._edit_selected_transcript).pack(
            fill="x", pady=2
        )
        ttk.Button(bcol, text="Remove Selected", command=self._remove_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Clear All", command=self._clear_files).pack(fill="x", pady=2)

        ttk.Label(self, text="Summarization prompt:").grid(row=4, column=0, sticky="w", **pad)
        self.prompt_combo = ttk.Combobox(self, state="readonly", width=50)
        self.prompt_combo.grid(row=4, column=1, sticky="ew", **pad)
        self.prompt_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_prompt_select())
        prompt_btns = ttk.Frame(self)
        prompt_btns.grid(row=4, column=2, columnspan=2, sticky="w", **pad)
        ttk.Button(prompt_btns, text="New", command=self._new_prompt).pack(side="left", padx=2)
        ttk.Button(prompt_btns, text="Edit", command=self._edit_prompt).pack(side="left", padx=2)
        ttk.Button(prompt_btns, text="Delete", command=self._delete_prompt).pack(
            side="left", padx=2
        )

        self.prompt_preview = tk.Text(self, height=8, wrap="word")
        self.prompt_preview.grid(row=5, column=0, columnspan=4, sticky="nsew", **pad)
        self.prompt_preview.config(state="disabled")

        ttk.Label(self, text="Output folder:").grid(row=6, column=0, sticky="w", **pad)
        self.out_var = tk.StringVar(value=cfg.get("last_output_folder", ""))
        ttk.Entry(self, textvariable=self.out_var, width=60).grid(
            row=6, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._browse_out).grid(
            row=6, column=3, sticky="w", **pad
        )

        self.go_btn = ttk.Button(
            self, text="Start Summarization", style=BTN_ACCENT, command=self._start
        )
        self.go_btn.grid(row=7, column=0, columnspan=4, sticky="ew", **pad)

        self.cancel_btn = ttk.Button(
            self, text="Cancel", command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.grid(row=8, column=0, sticky="w", **pad)
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, style=LBL_DIM).grid(
            row=8, column=1, columnspan=3, sticky="w", **pad
        )

        out_frame = ttk.LabelFrame(self, text="Output files")
        out_frame.grid(row=9, column=0, columnspan=4, sticky="ew", **pad)
        self.out_box = tk.Listbox(out_frame, height=4)
        self.out_box.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.out_box.bind("<Double-Button-1>", lambda _e: self._reveal_selected())
        ttk.Button(out_frame, text="Open Selected", command=self._open_selected).pack(
            side="left", padx=4
        )
        ttk.Button(out_frame, text="Copy Path", command=self._copy_selected).pack(
            side="left", padx=4
        )
        ttk.Button(
            out_frame, text="Open Folder", command=lambda: open_path_native(self.out_var.get())
        ).pack(side="left", padx=4)
        self.consolidate_btn = ttk.Button(
            out_frame,
            text="Consolidate into session summary (.docx)",
            command=self._consolidate,
            state="disabled",
        )
        self.consolidate_btn.pack(side="right", padx=4)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(5, weight=1)

        self._prompt_options: list[dict[str, Any]] = []
        self.refresh_prompts()
        self.refresh_sessions()

    def on_settings_changed(self):
        pass

    def on_show(self):
        self.refresh_sessions()
        self.refresh_prompts()

    def load_session(self, sid: int) -> None:
        """Populate from a saved session: select it, set speakers.json, and add
        its transcript_*.txt files. Used by History's 'Reopen in Summarize'."""
        self.refresh_sessions()
        if sid in self._session_index:
            self.session_combo.current(self._session_index.index(sid))
        s = db.get_session(sid) or {}
        spk = s.get("speakers_json_path")
        if spk:
            self.speakers_path = spk
            self.speakers_var.set(spk)
        folder = s.get("transcripts_folder")
        if folder and os.path.isdir(folder):
            import glob

            txts = sorted(
                p
                for p in glob.glob(os.path.join(folder, "*.txt"))
                if os.path.basename(p).startswith("transcript_")
            )
            self._set_transcript_files(txts)
        self.session_id = sid

    def _set_transcript_files(self, files: list[str]) -> None:
        self.transcript_files = []
        self.files_box.delete(0, "end")
        for p in files:
            self.transcript_files.append(p)
            self.files_box.insert("end", p)

    def _edit_selected_transcript(self):
        sel = list(self.files_box.curselection())
        if not sel:
            messagebox.showinfo("CampaignScribe", "Select a transcript file to edit.")
            return
        open_transcript_editor(self, self.files_box.get(sel[0]))

    def refresh_sessions(self):
        sessions = db.list_sessions()
        items = ["(no session — just produce files)"]
        self._session_index: list[int | None] = [None]
        for s in sessions:
            items.append(f"#{s['id']} — {s['display_name']}")
            self._session_index.append(s["id"])
        self.session_combo["values"] = items
        if self.session_combo.current() < 0:
            self.session_combo.current(0)

    def refresh_prompts(self):
        self._prompt_options = [
            {
                "id": None,
                "name": DEFAULT_PROMPT_NAME,
                "content": DEFAULT_SUMMARY_PROMPT,
                "is_default": True,
            }
        ]
        for p in db.list_user_prompts():
            self._prompt_options.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "content": p["content"],
                    "is_default": False,
                }
            )
        self.prompt_combo["values"] = [p["name"] for p in self._prompt_options]
        self.prompt_combo.current(0)
        self._on_prompt_select()

    def _on_prompt_select(self):
        idx = self.prompt_combo.current()
        if idx < 0:
            return
        sel = self._prompt_options[idx]
        self.prompt_preview.config(state="normal")
        self.prompt_preview.delete("1.0", "end")
        self.prompt_preview.insert("1.0", sel["content"])
        self.prompt_preview.config(state="disabled")

    def _new_prompt(self):
        dlg = PromptDialog(self, title="New Prompt")
        self.wait_window(dlg)
        if dlg.result:
            db.add_user_prompt(dlg.result["name"], dlg.result["content"])
            self.refresh_prompts()

    def _edit_prompt(self):
        idx = self.prompt_combo.current()
        if idx < 0:
            return
        sel = self._prompt_options[idx]
        if sel["is_default"]:
            messagebox.showinfo(
                "CampaignScribe",
                "The default prompt is read-only. Use 'New' to make a copy you can edit.",
            )
            return
        dlg = PromptDialog(self, name=sel["name"], content=sel["content"], title="Edit Prompt")
        self.wait_window(dlg)
        if dlg.result:
            db.update_user_prompt(sel["id"], dlg.result["name"], dlg.result["content"])
            self.refresh_prompts()

    def _delete_prompt(self):
        idx = self.prompt_combo.current()
        if idx < 0:
            return
        sel = self._prompt_options[idx]
        if sel["is_default"]:
            messagebox.showinfo("CampaignScribe", "The default prompt cannot be deleted.")
            return
        if not messagebox.askyesno("CampaignScribe", f"Delete prompt '{sel['name']}'?"):
            return
        db.delete_user_prompt(sel["id"])
        self.refresh_prompts()

    # ---------- file pickers ----------

    def _browse_speakers(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Select speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            try:
                speakers_io.load_speakers_json(path)
            except Exception as e:
                messagebox.showerror("CampaignScribe", str(e))
                return
            config.set_last_dir("json", path)
            self.speakers_path = path
            self.speakers_var.set(path)

    def _add_files(self):
        if self._busy:
            return
        paths = filedialog.askopenfilenames(
            title="Select transcript file(s)",
            initialdir=config.load_config().get("last_output_folder", "") or None,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        for p in paths:
            if p not in self.transcript_files:
                self.transcript_files.append(p)
                self.files_box.insert("end", p)

    def _remove_files(self):
        if self._busy:
            return
        for i in reversed(list(self.files_box.curselection())):
            self.files_box.delete(i)
            try:
                del self.transcript_files[i]
            except IndexError:
                pass

    def _clear_files(self):
        if self._busy:
            return
        self.transcript_files.clear()
        self.files_box.delete(0, "end")

    def _browse_out(self):
        if self._busy:
            return
        path = filedialog.askdirectory(
            title="Choose output folder",
            initialdir=config.load_config().get("last_output_folder", "") or None,
        )
        if path:
            self.out_var.set(path)

    # ---------- run ----------

    def _set_busy(self, b: bool):
        self._busy = b
        self.go_btn.config(state=("disabled" if b else "normal"))
        self.cancel_btn.config(state=("normal" if b else "disabled"))

    def _set_status(self, msg: str):
        self.after(0, lambda: self.status_var.set(msg))

    def _add_output(self, path: str):
        self.after(0, lambda: self.out_box.insert("end", path))

    def _cancel_run(self):
        if self._busy:
            self._cancel.set()
            self._set_status("Cancelling — will stop after current file.")

    def _start(self):
        if self._busy:
            return
        if not self.speakers_path:
            messagebox.showerror("CampaignScribe", "Pick a speakers.json first.")
            return
        if not self.transcript_files:
            messagebox.showerror("CampaignScribe", "Add at least one transcript file.")
            return
        if not config.get_anthropic_key():
            messagebox.showerror("CampaignScribe", "Add your Anthropic API key in Settings (⚙).")
            return
        out = (self.out_var.get() or "").strip()
        if not out:
            messagebox.showerror("CampaignScribe", "Choose an output folder.")
            return
        Path(out).mkdir(parents=True, exist_ok=True)
        cfg = config.load_config()
        cfg["last_output_folder"] = out
        cfg["last_speakers_json"] = self.speakers_path
        config.save_config(cfg)

        idx = self.session_combo.current()
        self.session_id = self._session_index[idx] if idx > 0 else None

        idx = self.prompt_combo.current()
        prompt_text = self._prompt_options[idx]["content"]

        self.out_box.delete(0, "end")
        self.part_summaries = []
        self.consolidated_path = None
        self.consolidate_btn.config(state="disabled")

        self._cancel.clear()
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(prompt_text,), daemon=True).start()

    def _worker(self, prompt_text: str):
        api_key = config.get_anthropic_key()
        try:
            speakers_doc = speakers_io.load_speakers_json(self.speakers_path)
        except Exception as e:
            self._set_status(f"speakers.json error: {e}")
            self.after(0, lambda: self._set_busy(False))
            return

        out = self.out_var.get().strip()
        for i, tpath in enumerate(self.transcript_files, start=1):
            if self._cancel.is_set():
                break
            self._set_status(
                f"[{i}/{len(self.transcript_files)}] Summarizing {os.path.basename(tpath)}…"
            )
            try:
                with open(tpath, encoding="utf-8") as f:
                    transcript = f.read()
                summary = summarizer.summarize_part(
                    transcript, speakers_doc, prompt_text, api_key, part_number=i
                )
                self.part_summaries.append(summary)
                out_path = os.path.join(out, f"summary_{i}.txt")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(summary)
                self._add_output(out_path)
            except Exception as e:
                self._set_status(f"Failed on {os.path.basename(tpath)}: {e}")
                self.after(0, lambda err=e: messagebox.showerror("CampaignScribe", str(err)))

        if self.part_summaries and not self._cancel.is_set():
            self._set_status(f"Done — {len(self.part_summaries)} part summaries written.")
            self.after(0, lambda: self.consolidate_btn.config(state="normal"))
        elif self._cancel.is_set():
            self._set_status("Cancelled.")
        else:
            self._set_status("Nothing produced.")

        self.after(0, lambda: self._set_busy(False))

    # ---------- consolidate ----------

    def _consolidate(self):
        if not self.part_summaries:
            return
        api_key = config.get_anthropic_key()
        if not api_key:
            messagebox.showerror("CampaignScribe", "API key missing.")
            return
        try:
            speakers_doc = speakers_io.load_speakers_json(self.speakers_path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        out = self.out_var.get().strip()
        if not out:
            return
        self._set_busy(True)
        self._set_status("Consolidating with Claude…")

        def worker():
            try:
                result = summarizer.consolidate_summaries(
                    self.part_summaries, speakers_doc, api_key
                )
                session_name = result.get("session_name") or "Session_Summary"
                fname = summarizer.safe_filename(session_name) + ".docx"
                out_path = os.path.join(out, fname)
                campaign = speakers_doc.get("campaign", "")
                summarizer.write_docx(
                    out_path,
                    session_name,
                    result.get("body", ""),
                    self.part_summaries,
                    campaign_name=campaign,
                )
                self.consolidated_path = out_path
                self._add_output(out_path)
                self._set_status(f"Saved {fname}")
                if self.session_id:
                    db.update_session(
                        self.session_id,
                        summary_path=out_path,
                        status="summarized",
                    )
            except Exception as e:
                self._set_status(f"Consolidation failed: {e}")
                self.after(0, lambda err=e: messagebox.showerror("CampaignScribe", str(err)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _open_selected(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        open_path_native(self.out_box.get(sel[0]))

    def _copy_selected(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        path = self.out_box.get(sel[0])
        self.clipboard_clear()
        self.clipboard_append(path)
        self._set_status(f"Copied path: {os.path.basename(path)}")

    def _reveal_selected(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        reveal_in_folder(self.out_box.get(sel[0]))
