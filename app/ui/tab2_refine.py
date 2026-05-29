"""Tab 5 — Speaker Refinement: improve an existing speakers.json from new audio."""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from app import config
from app.core import audio, speaker_id, speakers_io, transcriber
from app.ui.common import ScrollableFrame, open_path_native, short_path
from app.ui.theme import BTN_ACCENT, LBL_DIM, LBL_EYEBROW, LBL_HEADER


class Tab2Refine(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.audio_files: List[str] = []
        self.speakers_path: Optional[str] = None
        self.speakers_doc: Optional[Dict[str, Any]] = None
        self.suggestions: Optional[Dict[str, Any]] = None
        self._busy = False
        self._cancel = threading.Event()

        pad = {"padx": 10, "pady": 4}
        header_box = ttk.Frame(self)
        header_box.grid(row=0, column=0, columnspan=4, sticky="w", **pad)
        ttk.Label(header_box, text="Speaker Refinement", style=LBL_HEADER).pack(anchor="w")
        ttk.Label(
            header_box,
            text=("Feedback loop — analyzes new audio to improve your speakers.json. "
                  "Run it whenever you have fresh sessions, then re-Transcribe with the "
                  "better profile. It's not a post-Summarize step."),
            style=LBL_DIM, wraplength=820, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        ttk.Label(self, text="speakers.json:").grid(row=1, column=0, sticky="w", **pad)
        self.speakers_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.speakers_var, width=70, state="readonly").grid(
            row=1, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._browse_speakers).grid(
            row=1, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Audio files:").grid(row=2, column=0, sticky="nw", **pad)
        self.files_box = tk.Listbox(self, height=4, selectmode="extended")
        self.files_box.grid(row=2, column=1, columnspan=2, sticky="nsew", **pad)
        btn_col = ttk.Frame(self)
        btn_col.grid(row=2, column=3, sticky="nw", **pad)
        ttk.Button(btn_col, text="Add Files…", command=self._add_files).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Remove Selected", command=self._remove_selected).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Clear All", command=self._clear_files).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Load suggestions JSON…",
                   command=self._load_suggestions_file).pack(fill="x", pady=8)

        self.go_btn = ttk.Button(
            self, text="Analyze & Generate Suggestions",
            style=BTN_ACCENT, command=self._start
        )
        self.go_btn.grid(row=3, column=0, columnspan=4, sticky="ew", **pad)

        self.cancel_btn = ttk.Button(self, text="Cancel", command=self._cancel_run, state="disabled")
        self.cancel_btn.grid(row=4, column=0, sticky="w", **pad)
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=4, column=1, columnspan=3, sticky="ew", **pad)

        self.status_var = tk.StringVar(value="Pick a speakers.json and one or more audio files.")
        ttk.Label(self, textvariable=self.status_var, style=LBL_DIM).grid(
            row=5, column=0, columnspan=4, sticky="w", **pad
        )

        # Scrollable suggestions area
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=6, column=0, columnspan=4, sticky="nsew", **pad)

        self.save_btn = ttk.Button(
            self, text="Save Accepted Changes to speakers.json",
            style=BTN_ACCENT, command=self._save_changes, state="disabled",
        )
        self.save_btn.grid(row=7, column=0, columnspan=4, sticky="e", **pad)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(6, weight=1)

        # Per-suggestion accepted state, keyed by index/type
        self._accept_vars: Dict[str, tk.BooleanVar] = {}

    def on_settings_changed(self):
        pass

    # ---------- file pickers ----------

    def _browse_speakers(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Select speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.speakers_doc = speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Could not load speakers.json:\n{e}")
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

    def _remove_selected(self):
        if self._busy:
            return
        sel = list(self.files_box.curselection())
        for i in reversed(sel):
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

    # ---------- run ----------

    def _set_busy(self, b: bool):
        self._busy = b
        self.go_btn.config(state=("disabled" if b else "normal"))
        self.cancel_btn.config(state=("normal" if b else "disabled"))

    def _set_status(self, msg, pct=-1.0):
        def apply():
            self.status_var.set(msg)
            if pct >= 0:
                self.progress["value"] = max(0, min(100, pct * 100))
        self.after(0, apply)

    def _cancel_run(self):
        if self._busy:
            self._cancel.set()
            self._set_status("Cancelling…")

    def _start(self):
        if self._busy:
            return
        if not self.speakers_path or not self.speakers_doc:
            messagebox.showerror("CampaignScribe", "Pick a speakers.json first.")
            return
        if not self.audio_files:
            messagebox.showerror("CampaignScribe", "Add at least one audio file.")
            return
        if not config.get_anthropic_key():
            messagebox.showerror("CampaignScribe", "Add your Anthropic API key in Settings (⚙).")
            return
        self._cancel.clear()
        self._set_busy(True)
        self.save_btn.config(state="disabled")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        all_segments: List[Dict[str, Any]] = []
        wavs: List[str] = []
        pipeline = None
        try:
            cfg = config.load_config()
            pipeline = transcriber.TranscriptionPipeline(
                model_size=cfg.get("default_whisper_model", "small"),
                hf_token=hf,
            )
            for i, ap in enumerate(self.audio_files, start=1):
                if self._cancel.is_set():
                    raise InterruptedError("Cancelled")
                self._set_status(
                    f"[{i}/{len(self.audio_files)}] Converting {os.path.basename(ap)}…",
                    (i - 1) / len(self.audio_files),
                )
                wav = audio.convert_to_wav(ap)
                wavs.append(wav)
                segments = pipeline.transcribe_file(
                    wav,
                    num_speakers=int(cfg.get("default_num_speakers", 5)),
                    progress=lambda s, p: self._set_status(
                        f"[{i}/{len(self.audio_files)}] {s}",
                        (i - 1 + p) / max(1, len(self.audio_files)),
                    ),
                )
                all_segments.extend(segments)

            self._set_status("Asking Claude for refinement suggestions…", 0.95)
            self.suggestions = speaker_id.refine_speakers(
                all_segments, self.speakers_doc, api_key
            )
            self._set_status("Done. Review suggestions below.", 1.0)
            self.after(0, self._render_suggestions)
        except InterruptedError:
            self._set_status("Cancelled.", 0.0)
        except Exception as e:
            self._set_status(f"Error: {e}", 0.0)
            self.after(0, lambda: messagebox.showerror("CampaignScribe", str(e)))
        finally:
            if pipeline is not None:
                try:
                    pipeline.close()
                except Exception:
                    pass
            for w in wavs:
                try:
                    os.remove(w)
                except OSError:
                    pass
            self.after(0, lambda: self._set_busy(False))

    # ---------- suggestions UI ----------

    def _load_suggestions_file(self):
        path = filedialog.askopenfilename(
            title="Select speakers_improvements_*.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        if not self.speakers_path or not self.speakers_doc:
            messagebox.showerror("CampaignScribe", "Pick a speakers.json first.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.suggestions = json.load(f)
            self._render_suggestions()
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Could not load file:\n{e}")

    def _render_suggestions(self):
        for w in list(self.scroll.inner.winfo_children()):
            w.destroy()
        self._accept_vars.clear()
        s = self.suggestions or {}

        def header(text):
            lbl = ttk.Label(self.scroll.inner, text=text, style=LBL_EYEBROW)
            lbl.pack(anchor="w", padx=4, pady=(8, 4))

        improvements = s.get("improvements", [])
        new_speakers = s.get("new_speakers", [])
        ignores = s.get("suggested_ignores", [])

        if not improvements and not new_speakers and not ignores:
            ttk.Label(self.scroll.inner, text="(No suggestions returned.)").pack(
                anchor="w", padx=4, pady=8
            )
            return

        if improvements:
            header("EXISTING SPEAKER IMPROVEMENTS")
            for idx, imp in enumerate(improvements):
                key = f"imp_{idx}"
                v = tk.BooleanVar(value=True)
                self._accept_vars[key] = v
                box = ttk.LabelFrame(
                    self.scroll.inner,
                    text=f"{imp.get('existing_player_name', '?')}  "
                         f"({imp.get('source_speaker_id', '?')}, "
                         f"confidence={imp.get('confidence', '?')})",
                )
                box.pack(fill="x", padx=4, pady=4)
                for pat in imp.get("new_speech_patterns", []):
                    ttk.Label(box, text=f"+ pattern: {pat}", wraplength=720, justify="left").pack(
                        anchor="w", padx=8, pady=1
                    )
                for q in imp.get("new_sample_quotes", []):
                    ttk.Label(box, text=f"+ quote:   {q}", wraplength=720, justify="left").pack(
                        anchor="w", padx=8, pady=1
                    )
                ttk.Checkbutton(box, text="Accept", variable=v).pack(anchor="w", padx=8, pady=2)

        if new_speakers:
            header("NEW SPEAKERS DETECTED")
            for idx, ns in enumerate(new_speakers):
                key = f"new_{idx}"
                v = tk.BooleanVar(value=False)
                self._accept_vars[key] = v
                box = ttk.LabelFrame(
                    self.scroll.inner,
                    text=f"{ns.get('source_speaker_id', '?')}  "
                         f"(role={ns.get('inferred_role', '?')}, "
                         f"confidence={ns.get('confidence', '?')})",
                )
                box.pack(fill="x", padx=4, pady=4)
                ttk.Label(box, text=f"Suggested name: {ns.get('suggested_display_name', '?')}").pack(
                    anchor="w", padx=8
                )
                ttk.Label(box, text=f"Notes: {ns.get('notes', '')}", wraplength=720).pack(
                    anchor="w", padx=8
                )
                for pat in ns.get("speech_patterns", []):
                    ttk.Label(box, text=f"+ pattern: {pat}", wraplength=720).pack(anchor="w", padx=8)
                for q in ns.get("sample_quotes", []):
                    ttk.Label(box, text=f"+ quote:   {q}", wraplength=720).pack(anchor="w", padx=8)
                ttk.Checkbutton(box, text="Add to players", variable=v).pack(
                    anchor="w", padx=8, pady=2
                )

        if ignores:
            header("SUGGESTED SPEAKERS TO IGNORE")
            for idx, ig in enumerate(ignores):
                key = f"ig_{idx}"
                v = tk.BooleanVar(value=False)
                self._accept_vars[key] = v
                box = ttk.LabelFrame(self.scroll.inner, text=ig.get("source_speaker_id", "?"))
                box.pack(fill="x", padx=4, pady=4)
                ttk.Label(box, text=f"Reason: {ig.get('reason', '')}", wraplength=720).pack(
                    anchor="w", padx=8
                )
                if ig.get("sample_quote"):
                    ttk.Label(box, text=f"Sample: {ig.get('sample_quote')}", wraplength=720).pack(
                        anchor="w", padx=8
                    )
                ttk.Checkbutton(box, text="Mark as ignored (add to known_non_players)",
                                variable=v).pack(anchor="w", padx=8, pady=2)

        self.save_btn.config(state="normal")

    def _save_changes(self):
        if not self.speakers_path or not self.speakers_doc or not self.suggestions:
            return
        doc = self.speakers_doc
        s = self.suggestions

        # Improvements: append patterns/quotes to matching players (by player_name)
        for idx, imp in enumerate(s.get("improvements", [])):
            if not self._accept_vars.get(f"imp_{idx}", tk.BooleanVar(value=False)).get():
                continue
            target_name = (imp.get("existing_player_name") or "").strip().lower()
            for player in doc.get("players", []):
                if (player.get("player_name") or "").strip().lower() == target_name:
                    patterns = list(player.get("speech_patterns", []))
                    for p in imp.get("new_speech_patterns", []):
                        if p not in patterns:
                            patterns.append(p)
                    player["speech_patterns"] = patterns
                    quotes = list(player.get("sample_quotes", []))
                    for q in imp.get("new_sample_quotes", []):
                        if q not in quotes:
                            quotes.append(q)
                    if quotes:
                        player["sample_quotes"] = quotes
                    break

        # New speakers
        for idx, ns in enumerate(s.get("new_speakers", [])):
            if not self._accept_vars.get(f"new_{idx}", tk.BooleanVar(value=False)).get():
                continue
            doc.setdefault("players", []).append({
                "player_name": ns.get("suggested_display_name") or ns.get("source_speaker_id"),
                "role": ns.get("inferred_role", "Player"),
                "character_name": "",
                "character_class": "",
                "notes": ns.get("notes", ""),
                "speech_patterns": ns.get("speech_patterns", []),
                "sample_quotes": ns.get("sample_quotes", []),
                "source_speaker_id": ns.get("source_speaker_id", ""),
            })

        # Ignored speakers
        for idx, ig in enumerate(s.get("suggested_ignores", [])):
            if not self._accept_vars.get(f"ig_{idx}", tk.BooleanVar(value=False)).get():
                continue
            doc.setdefault("known_non_players", []).append({
                "name": ig.get("source_speaker_id"),
                "role": "ignore",
                "notes": ig.get("reason", ""),
                "speech_patterns": [ig.get("sample_quote")] if ig.get("sample_quote") else [],
                "source_speaker_id": ig.get("source_speaker_id", ""),
            })

        try:
            speakers_io.save_speakers_json(self.speakers_path, doc)
            messagebox.showinfo(
                "CampaignScribe", f"Updated {self.speakers_path}"
            )
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Save failed:\n{e}")
