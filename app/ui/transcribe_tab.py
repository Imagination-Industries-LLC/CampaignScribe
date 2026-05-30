"""Transcription: WhisperX + diarization + Claude speaker ID."""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from app import config
from app.core import audio, privacy, speaker_id, speakers_io, transcriber
from app.data import db
from app.ui.common import (
    add_privacy_note,
    open_path_native,
    open_transcript_editor,
    reveal_in_folder,
)
from app.ui.theme import BTN_ACCENT, LBL_DIM, LBL_HEADER

STATE_ICONS = {
    "queued": "⏳",
    "converting": "🔄",
    "transcribing": "🔄",
    "identifying": "🔄",
    "complete": "✅",
    "failed": "❌",
}


class TranscribeTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.audio_files: list[str] = []
        self.speakers_path: str | None = None
        self.output_dir: str | None = None
        self.session_id: int | None = None
        self.row_items: dict[str, str] = {}  # path -> tree iid
        self.results: list[dict[str, str]] = []  # output files
        self._busy = False
        self._cancel = threading.Event()

        cfg = config.load_config()
        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Transcription", style=LBL_HEADER).grid(
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
        self.session_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_session_selected())
        ttk.Button(self, text="Refresh", command=self.refresh_sessions).grid(
            row=2, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Audio files:").grid(row=3, column=0, sticky="nw", **pad)
        self.files_box = tk.Listbox(self, height=4, selectmode="extended")
        self.files_box.grid(row=3, column=1, columnspan=2, sticky="nsew", **pad)
        bcol = ttk.Frame(self)
        bcol.grid(row=3, column=3, sticky="nw", **pad)
        ttk.Button(bcol, text="Add Files…", command=self._add_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Remove Selected", command=self._remove_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Clear All", command=self._clear_files).pack(fill="x", pady=2)

        ttk.Label(self, text="Whisper model:").grid(row=4, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(value=cfg.get("default_whisper_model", "large-v3"))
        ttk.Combobox(
            self,
            textvariable=self.model_var,
            state="readonly",
            width=12,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(self, text="# speakers:").grid(row=4, column=2, sticky="e", **pad)
        self.spk_var = tk.IntVar(value=int(cfg.get("default_num_speakers", 5)))
        ttk.Spinbox(self, from_=1, to=20, textvariable=self.spk_var, width=8).grid(
            row=4, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Output folder:").grid(row=5, column=0, sticky="w", **pad)
        self.out_var = tk.StringVar(value=cfg.get("last_output_folder", ""))
        ttk.Entry(self, textvariable=self.out_var, width=60).grid(
            row=5, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._browse_out).grid(
            row=5, column=3, sticky="w", **pad
        )

        self.go_btn = ttk.Button(
            self, text="Start Transcription", style=BTN_ACCENT, command=self._start
        )
        self.go_btn.grid(row=6, column=0, columnspan=4, sticky="ew", **pad)

        self.cancel_btn = ttk.Button(
            self, text="Cancel", command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.grid(row=7, column=0, sticky="w", **pad)
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, style=LBL_DIM).grid(
            row=7, column=1, columnspan=3, sticky="w", **pad
        )

        cols = ("file", "state", "detail")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        self.tree.heading("file", text="File")
        self.tree.heading("state", text="State")
        self.tree.heading("detail", text="Detail")
        self.tree.column("file", width=380, anchor="w")
        self.tree.column("state", width=120, anchor="w")
        self.tree.column("detail", width=300, anchor="w")
        self.tree.grid(row=8, column=0, columnspan=4, sticky="nsew", **pad)

        out_label = ttk.LabelFrame(self, text="Output files")
        out_label.grid(row=9, column=0, columnspan=4, sticky="ew", **pad)
        self.out_box = tk.Listbox(out_label, height=4)
        self.out_box.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.out_box.bind("<Double-Button-1>", lambda _e: self._reveal_selected_output())
        ttk.Button(out_label, text="Open Selected", command=self._open_selected_output).pack(
            side="left", padx=4
        )
        ttk.Button(out_label, text="Copy Path", command=self._copy_selected_output).pack(
            side="left", padx=4
        )
        ttk.Button(out_label, text="Edit Transcript", command=self._edit_selected_output).pack(
            side="left", padx=4
        )
        ttk.Button(
            out_label,
            text="Open Folder",
            command=lambda: open_path_native(self.output_dir or self.out_var.get()),
        ).pack(side="left", padx=4)
        ttk.Button(
            out_label, text="→ Send improvements to Refine tab", command=self._send_to_refine
        ).pack(side="left", padx=4)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(8, weight=1)

        self.refresh_sessions()

        self._privacy_note = add_privacy_note(self, privacy.NOTE_SAMPLES)

    def on_settings_changed(self):
        cfg = config.load_config()
        self.spk_var.set(int(cfg.get("default_num_speakers", 5)))
        self.model_var.set(cfg.get("default_whisper_model", "large-v3"))

    def on_show(self):
        self.refresh_sessions()

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

    def _on_session_selected(self):
        idx = self.session_combo.current()
        sid = self._session_index[idx] if idx > 0 else None
        if sid:
            self.load_session(sid, refresh=False)

    def load_session(self, sid: int, refresh: bool = True) -> None:
        """Populate the form from a saved session: select it, load its source
        audio files and speakers.json. Used by the session dropdown and by
        History's 'Reopen in Transcribe'."""
        if refresh:
            self.refresh_sessions()
        if sid in self._session_index:
            self.session_combo.current(self._session_index.index(sid))
        s = db.get_session(sid) or {}
        try:
            files = json.loads(s.get("source_audio_files") or "[]")
        except Exception:
            files = []
        self._set_audio_files(files)
        spk = s.get("speakers_json_path")
        if spk:
            self.speakers_path = spk
            self.speakers_var.set(spk)
        self.session_id = sid

    def _set_audio_files(self, files: list[str]) -> None:
        self.audio_files = []
        self.files_box.delete(0, "end")
        missing = []
        for p in files:
            self.audio_files.append(p)
            exists = os.path.exists(p)
            self.files_box.insert("end", p if exists else f"{p}   [missing]")
            if not exists:
                missing.append(p)
        if missing:
            messagebox.showwarning(
                "CampaignScribe",
                "Some audio files from this session no longer exist on disk:\n\n"
                + "\n".join(os.path.basename(m) for m in missing),
            )

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
            title="Select audio file(s)",
            initialdir=config.get_last_dir("audio") or None,
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            config.set_last_dir("audio", paths[0])
        for p in paths:
            if p not in self.audio_files:
                self.audio_files.append(p)
                self.files_box.insert("end", p)

    def _remove_files(self):
        if self._busy:
            return
        for i in reversed(list(self.files_box.curselection())):
            self.files_box.delete(i)
            try:
                del self.audio_files[i]
            except IndexError:
                pass

    def _clear_files(self):
        if self._busy:
            return
        self.audio_files.clear()
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

    def _set_row(self, path: str, state: str, detail: str = ""):
        iid = self.row_items.get(path)

        def apply():
            nonlocal iid
            if iid is None:
                iid = self.tree.insert(
                    "",
                    "end",
                    values=(
                        os.path.basename(path),
                        f"{STATE_ICONS.get(state, '')} {state}",
                        detail,
                    ),
                )
                self.row_items[path] = iid
            else:
                self.tree.item(
                    iid,
                    values=(
                        os.path.basename(path),
                        f"{STATE_ICONS.get(state, '')} {state}",
                        detail,
                    ),
                )

        self.after(0, apply)

    def _add_output(self, path: str):
        self.results.append({"path": path})
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
        if not self.audio_files:
            messagebox.showerror("CampaignScribe", "Add at least one audio file.")
            return
        api_key = config.get_anthropic_key()
        if not api_key:
            messagebox.showerror("CampaignScribe", "Add your Anthropic API key in Settings (⚙).")
            return
        if not config.get_huggingface_token():
            messagebox.showerror(
                "CampaignScribe",
                "Diarization requires a HuggingFace token.\n\n"
                "1) Create a token at https://huggingface.co/settings/tokens\n"
                "2) Accept the license on https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                "3) Paste the token in Settings (⚙).",
            )
            return
        out = (self.out_var.get() or "").strip()
        if not out:
            messagebox.showerror("CampaignScribe", "Choose an output folder.")
            return
        self.output_dir = out
        Path(out).mkdir(parents=True, exist_ok=True)
        cfg = config.load_config()
        cfg["last_output_folder"] = out
        cfg["last_speakers_json"] = self.speakers_path
        config.save_config(cfg)

        # Resolve linked session id
        idx = self.session_combo.current()
        self.session_id = self._session_index[idx] if idx > 0 else None

        # Reset UI
        self.tree.delete(*self.tree.get_children())
        self.row_items.clear()
        self.out_box.delete(0, "end")
        self.results.clear()
        for f in self.audio_files:
            self._set_row(f, "queued")

        self._cancel.clear()
        self._set_busy(True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        try:
            speakers_doc = speakers_io.load_speakers_json(self.speakers_path)
            ignored_ids = [
                n.get("source_speaker_id", "")
                for n in speakers_doc.get("known_non_players", [])
                if n.get("source_speaker_id")
            ]
        except Exception as e:
            self._set_status(f"speakers.json error: {e}")
            self.after(0, lambda: self._set_busy(False))
            return

        pipeline = transcriber.TranscriptionPipeline(
            model_size=self.model_var.get(),
            hf_token=hf,
        )

        all_segments: list[dict[str, Any]] = []
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        for i, ap in enumerate(self.audio_files, start=1):
            if self._cancel.is_set():
                self._set_row(ap, "failed", "cancelled")
                continue
            self._set_status(f"[{i}/{len(self.audio_files)}] {os.path.basename(ap)}")
            wav: str | None = None
            try:
                self._set_row(ap, "converting")
                wav = audio.convert_to_wav(ap)

                self._set_row(ap, "transcribing", "WhisperX + diarization")

                def progress_cb(stage: str, _pct: float, _ap: str = ap):
                    if self._cancel.is_set():
                        raise InterruptedError("Cancelled")
                    self._set_row(_ap, "transcribing", stage)

                segments = pipeline.transcribe_file(
                    wav, num_speakers=int(self.spk_var.get()), progress=progress_cb
                )
                # Save raw JSON
                json_path = os.path.join(self.output_dir, f"transcript_{run_ts}_{i}.json")
                transcriber.save_segments_json(segments, json_path)
                self._add_output(json_path)

                self._set_row(ap, "identifying", "Claude speaker mapping")
                mapping = speaker_id.identify_speakers(segments, speakers_doc, api_key)
                map_path = os.path.join(self.output_dir, f"speaker_mapping_{run_ts}_{i}.json")
                with open(map_path, "w", encoding="utf-8") as f:
                    json.dump(mapping, f, indent=2, ensure_ascii=False)
                self._add_output(map_path)

                txt = speaker_id.format_segments_to_text(segments, mapping, ignored_ids)
                txt_path = os.path.join(self.output_dir, f"transcript_{run_ts}_{i}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(txt)
                self._add_output(txt_path)

                all_segments.extend(segments)
                self._set_row(ap, "complete", f"transcript_{run_ts}_{i}.txt")
            except InterruptedError:
                self._set_row(ap, "failed", "cancelled")
            except Exception as e:
                config.log_exception(f"transcribe_tab[{os.path.basename(ap)}]", e)
                self._set_row(ap, "failed", str(e)[:100])
            finally:
                if wav and os.path.exists(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass

        # After all files: produce speakers_improvements
        if all_segments and not self._cancel.is_set():
            try:
                self._set_status("Generating speaker improvement suggestions…")
                imp = speaker_id.refine_speakers(all_segments, speakers_doc, api_key)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                imp_path = os.path.join(self.output_dir, f"speakers_improvements_{ts}.json")
                with open(imp_path, "w", encoding="utf-8") as f:
                    json.dump(imp, f, indent=2, ensure_ascii=False)
                self._add_output(imp_path)
                self._set_status(
                    "Done. Speaker-improvement suggestions saved — open the Refine tab "
                    "to review them and fold them into your profile before your "
                    "next session."
                )
            except Exception as e:
                self._set_status(f"Done — improvements step failed: {e}")
        else:
            self._set_status("Done.")

        # Update session record
        if self.session_id:
            try:
                db.update_session(
                    self.session_id,
                    transcripts_folder=self.output_dir,
                    speakers_json_path=self.speakers_path,
                    status="transcribed",
                )
            except Exception:
                pass

        try:
            pipeline.close()
        except Exception:
            pass
        self.after(0, lambda: self._set_busy(False))

    def _open_selected_output(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        path = self.out_box.get(sel[0])
        open_path_native(path)

    def _edit_selected_output(self):
        sel = list(self.out_box.curselection())
        if not sel:
            messagebox.showinfo("CampaignScribe", "Select a transcript .txt in the list first.")
            return
        path = self.out_box.get(sel[0])
        if not path.lower().endswith(".txt"):
            messagebox.showinfo("CampaignScribe", "Only transcript .txt files are editable here.")
            return
        open_transcript_editor(self, path)

    def _copy_selected_output(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        path = self.out_box.get(sel[0])
        self.clipboard_clear()
        self.clipboard_append(path)
        self._set_status(f"Copied path: {os.path.basename(path)}")

    def _reveal_selected_output(self):
        sel = list(self.out_box.curselection())
        if not sel:
            return
        reveal_in_folder(self.out_box.get(sel[0]))

    def _send_to_refine(self):
        # Find the most recent speakers_improvements_*.json in results
        target = next(
            (
                r["path"]
                for r in reversed(self.results)
                if os.path.basename(r["path"]).startswith("speakers_improvements_")
            ),
            None,
        )
        if not target:
            messagebox.showinfo("CampaignScribe", "No improvements file produced yet.")
            return
        try:
            with open(target, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        # Push into Refine tab
        refine_tab = self.app.refine_tab
        if not refine_tab.speakers_doc:
            try:
                refine_tab.speakers_doc = speakers_io.load_speakers_json(self.speakers_path)
                refine_tab.speakers_path = self.speakers_path
                refine_tab.speakers_var.set(self.speakers_path)
            except Exception as e:
                messagebox.showerror("CampaignScribe", str(e))
                return
        refine_tab.suggestions = doc
        refine_tab._render_suggestions()
        self.app.jump_to_tab(4)
