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
from app.core import (
    audio,
    library,
    llm,
    models,
    multitrack,
    privacy,
    speaker_id,
    speakers_io,
    transcriber,
)
from app.data import db
from app.ui.common import (
    ScrollableFrame,
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
        self.track_meta: dict[str, dict] = {}  # path -> {speaker, shared_mic}
        self.speakers_path: str | None = None
        self.output_dir: str | None = None
        self.session_id: int | None = None
        self.row_items: dict[str, str] = {}  # path -> tree iid
        self.results: list[dict[str, str]] = []  # output files
        self._busy = False
        self._cancel = threading.Event()
        self._run_params: dict = {}
        self._run_mode = "mixed"

        self._scroll = ScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True)
        body = self._scroll.inner

        cfg = config.load_config()
        pad = {"padx": 10, "pady": 4}
        ttk.Label(body, text="Transcription", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(body, text="Session (optional):").grid(row=1, column=0, sticky="w", **pad)
        self.session_combo = ttk.Combobox(body, state="readonly", width=60)
        self.session_combo.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        self.session_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_session_selected())
        ttk.Button(body, text="Refresh", command=self.refresh_sessions).grid(
            row=1, column=3, sticky="w", **pad
        )

        ttk.Label(body, text="Audio files:").grid(row=2, column=0, sticky="nw", **pad)
        self.mode_var = tk.StringVar(value="mixed")
        mode_frame = ttk.Frame(body)
        mode_frame.grid(row=2, column=1, columnspan=3, sticky="w", **pad)
        ttk.Radiobutton(
            mode_frame,
            text="Mixed recording",
            variable=self.mode_var,
            value="mixed",
            command=self._apply_mode,
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            mode_frame,
            text="One file per speaker",
            variable=self.mode_var,
            value="tracks",
            command=self._apply_mode,
        ).pack(side="left")
        self.files_box = tk.Listbox(body, height=4, selectmode="extended")
        self.files_box.grid(row=3, column=1, columnspan=2, sticky="nsew", **pad)
        self.tracks_table = ttk.Treeview(
            body, columns=("file", "speaker", "shared"), show="headings", height=4
        )
        self.tracks_table.heading("file", text="File")
        self.tracks_table.heading("speaker", text="Speaker")
        self.tracks_table.heading("shared", text="Shared mic")
        self.tracks_table.column("file", width=300, anchor="w")
        self.tracks_table.column("speaker", width=140, anchor="w")
        self.tracks_table.column("shared", width=80, anchor="center")
        self.tracks_table.grid(row=3, column=1, columnspan=2, sticky="nsew", **pad)
        self.tracks_table.grid_remove()
        self.tracks_table.bind("<Double-1>", lambda _e: self._edit_track())
        bcol = ttk.Frame(body)
        bcol.grid(row=3, column=3, sticky="nw", **pad)
        ttk.Button(bcol, text="Add Files…", command=self._add_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Remove Selected", command=self._remove_files).pack(fill="x", pady=2)
        ttk.Button(bcol, text="Clear All", command=self._clear_files).pack(fill="x", pady=2)
        self.edit_track_btn = ttk.Button(bcol, text="Edit track…", command=self._edit_track)

        ttk.Label(body, text="Whisper model:").grid(row=4, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(value=cfg.get("default_whisper_model", "large-v3"))
        ttk.Combobox(
            body,
            textvariable=self.model_var,
            state="readonly",
            width=12,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=4, column=1, sticky="w", **pad)

        self.spk_label = ttk.Label(body, text="# speakers:")
        self.spk_label.grid(row=4, column=2, sticky="e", **pad)
        self.spk_var = tk.IntVar(value=int(cfg.get("default_num_speakers", 5)))
        ttk.Spinbox(body, from_=1, to=20, textvariable=self.spk_var, width=8).grid(
            row=4, column=3, sticky="w", **pad
        )

        ttk.Label(body, text="Output folder:").grid(row=5, column=0, sticky="w", **pad)
        self.out_var = tk.StringVar(value=cfg.get("last_output_folder", ""))
        ttk.Entry(body, textvariable=self.out_var, width=60).grid(
            row=5, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(body, text="Browse…", command=self._browse_out).grid(
            row=5, column=3, sticky="w", **pad
        )

        self.go_btn = ttk.Button(
            body, text="Start Transcription", style=BTN_ACCENT, command=self._start
        )
        self.go_btn.grid(row=6, column=0, columnspan=4, sticky="ew", **pad)

        self.cancel_btn = ttk.Button(
            body, text="Cancel", command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.grid(row=7, column=0, sticky="w", **pad)
        self.status_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.status_var, style=LBL_DIM).grid(
            row=7, column=1, columnspan=3, sticky="w", **pad
        )

        cols = ("file", "state", "detail")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=8)
        self.tree.heading("file", text="File")
        self.tree.heading("state", text="State")
        self.tree.heading("detail", text="Detail")
        self.tree.column("file", width=380, anchor="w")
        self.tree.column("state", width=120, anchor="w")
        self.tree.column("detail", width=300, anchor="w")
        self.tree.grid(row=8, column=0, columnspan=4, sticky="nsew", **pad)

        out_label = ttk.LabelFrame(body, text="Output files")
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

        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(8, weight=1)

        self.active_slug: str | None = None
        self.refresh_sessions()

        self._privacy_note = add_privacy_note(
            body, privacy.note_samples(llm.active_preset().vendor_label)
        )

    def on_settings_changed(self):
        cfg = config.load_config()
        self.spk_var.set(int(cfg.get("default_num_speakers", 5)))
        self.model_var.set(cfg.get("default_whisper_model", "large-v3"))
        self._privacy_note.config(text=privacy.note_samples(llm.active_preset().vendor_label))

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

    def load_for_session(self, session: dict, run_params: dict | None = None) -> None:
        """Set the active session and derive speakers.json from its campaign_slug
        (current library version), falling back to the session's stored path."""
        self.session_id = int(session["id"])
        self.active_slug = session.get("campaign_slug")
        self.speakers_path = self._resolve_speakers_path(session)
        # populate audio/transcript inputs from the session as load_session did
        self.load_session(self.session_id)
        # store run_params AFTER load_session (which resets _run_params to {})
        self._run_params = run_params or {}
        if self._run_params.get("mode") == "tracks":
            self.mode_var.set("tracks")
            self._apply_mode()

    def _resolve_speakers_path(self, session: dict) -> str | None:
        slug = session.get("campaign_slug")
        if slug:
            try:
                return str(library.current_version_path(slug))
            except FileNotFoundError:
                pass
        return session.get("speakers_json_path")

    def load_session(self, sid: int, refresh: bool = True) -> None:
        """Populate the form from a saved session: select it, load its source
        audio files and speakers.json. Used by the session dropdown and by
        History's 'Reopen in Transcribe'."""
        if refresh:
            self.refresh_sessions()
        if sid in self._session_index:
            self.session_combo.current(self._session_index.index(sid))
        s = db.get_session(sid) or {}
        self.active_slug = s.get("campaign_slug")
        try:
            files = json.loads(s.get("source_audio_files") or "[]")
        except Exception:
            files = []
        self._set_audio_files(files)
        self.speakers_path = self._resolve_speakers_path(s)
        self.session_id = sid
        # Standalone open (session dropdown / History reopen): no ①-launch params,
        # so the run falls back to the spinbox count. load_for_session re-sets this after.
        self._run_params = {}

    def _set_audio_files(self, files: list[str]) -> None:
        self.audio_files = []
        self.files_box.delete(0, "end")
        self.track_meta.clear()
        self.tracks_table.delete(*self.tracks_table.get_children())
        missing = []
        for p in files:
            self.audio_files.append(p)
            self._track_row_add(p)
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
                self._track_row_add(p)

    def _remove_files(self):
        if self._busy:
            return
        if self.mode_var.get() == "tracks":
            picked = [
                self.audio_files.index(p)
                for p in self.tracks_table.selection()
                if p in self.audio_files
            ]
        else:
            picked = list(self.files_box.curselection())
        for i in sorted(picked, reverse=True):
            self.files_box.delete(i)
            try:
                self._track_row_remove(self.audio_files[i])
                del self.audio_files[i]
            except IndexError:
                pass

    def _clear_files(self):
        if self._busy:
            return
        self.audio_files.clear()
        self.files_box.delete(0, "end")
        self.track_meta.clear()
        self.tracks_table.delete(*self.tracks_table.get_children())

    # ---------- multi-track mode ----------

    def _apply_mode(self):
        """Show the list or the track table; never touches audio_files."""
        if self.mode_var.get() == "tracks":
            self.files_box.grid_remove()
            self.tracks_table.grid()
            self.edit_track_btn.pack(fill="x", pady=2)
            self.spk_label.config(text="# speakers per shared mic")
        else:
            self.tracks_table.grid_remove()
            self.files_box.grid()
            self.edit_track_btn.pack_forget()
            self.spk_label.config(text="# speakers:")

    @staticmethod
    def _shared_glyph(shared: bool) -> str:
        return "☑" if shared else "☐"

    def _track_values(self, path: str) -> tuple[str, str, str]:
        meta = self.track_meta[path]
        return (os.path.basename(path), meta["speaker"], self._shared_glyph(meta["shared_mic"]))

    def _track_row_add(self, path: str) -> None:
        """Keep track_meta and tracks_table in step with audio_files."""
        self.track_meta.setdefault(
            path, {"speaker": multitrack.name_from_filename(path), "shared_mic": False}
        )
        if not self.tracks_table.exists(path):
            self.tracks_table.insert("", "end", iid=path, values=self._track_values(path))

    def _track_row_remove(self, path: str) -> None:
        self.track_meta.pop(path, None)
        if self.tracks_table.exists(path):
            self.tracks_table.delete(path)

    def _tracks(self) -> list[multitrack.Track]:
        return [
            multitrack.Track(
                p, self.track_meta[p]["speaker"].strip(), self.track_meta[p]["shared_mic"]
            )
            for p in self.audio_files
        ]

    def _set_track(self, path: str, speaker: str | None = None, shared_mic: bool | None = None):
        meta = self.track_meta.get(path)
        if meta is None:
            return
        if speaker is not None:
            meta["speaker"] = speaker
        if shared_mic is not None:
            meta["shared_mic"] = bool(shared_mic)
        if self.tracks_table.exists(path):
            self.tracks_table.item(path, values=self._track_values(path))

    def _player_names(self) -> list[str]:
        try:
            doc = library.get_current_doc(self.active_slug) if self.active_slug else {}
            names = [p.get("player_name", "") for p in doc.get("players", [])]
            return [n for n in names if n]
        except Exception:
            return []

    def _edit_track(self):
        sel = self.tracks_table.selection()
        if sel:
            self._open_track_dialog(sel[0])

    def _open_track_dialog(self, path: str) -> tk.Toplevel:
        meta = self.track_meta[path]
        dlg = tk.Toplevel(self)
        dlg.title("Edit track")
        dlg.transient(self.winfo_toplevel())
        speaker_var = tk.StringVar(value=meta["speaker"])
        shared_var = tk.BooleanVar(value=bool(meta["shared_mic"]))
        ttk.Label(dlg, text=os.path.basename(path)).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 4), sticky="w"
        )
        ttk.Label(dlg, text="Speaker:").grid(row=1, column=0, padx=10, pady=4, sticky="w")
        ttk.Combobox(dlg, textvariable=speaker_var, values=self._player_names(), width=28).grid(
            row=1, column=1, padx=10, pady=4, sticky="ew"
        )
        ttk.Checkbutton(dlg, text="Shared mic", variable=shared_var).grid(
            row=2, column=1, padx=10, pady=4, sticky="w"
        )

        def ok():
            self._set_track(path, speaker=speaker_var.get(), shared_mic=shared_var.get())
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="e")
        ok_btn = ttk.Button(btns, text="OK", command=ok)
        ok_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)
        # Exposed for tests (they never wait on the dialog).
        dlg.speaker_var = speaker_var  # type: ignore[attr-defined]
        dlg.shared_var = shared_var  # type: ignore[attr-defined]
        dlg.ok_btn = ok_btn  # type: ignore[attr-defined]
        dlg.grab_set()
        return dlg

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
            slug = getattr(self, "active_slug", None)
            if slug and hasattr(self.app, "open_edit_profile"):
                if messagebox.askyesno(
                    "Build speaker profile?",
                    "This campaign has no speaker profile yet.\n\n"
                    "Discover speakers from your audio to build one? You'll review and "
                    "edit the profile in the next window, then come back here and click "
                    "Transcribe.",
                ):
                    audio = self.audio_files[0] if self.audio_files else None
                    self.app.open_edit_profile(slug, discover_audio=audio)
                return
            messagebox.showerror(
                "CampaignScribe",
                "No speaker profile loaded — open a session from a campaign in Home, "
                "or build a profile first.",
            )
            return
        if not self.audio_files:
            messagebox.showerror("CampaignScribe", "Add at least one audio file.")
            return
        if self.mode_var.get() == "tracks":
            if len(self.audio_files) < 2:
                messagebox.showerror(
                    "CampaignScribe",
                    "Add at least two files (one per speaker), or switch to Mixed recording.",
                )
                return
            if any(not t.speaker for t in self._tracks()):
                messagebox.showerror("CampaignScribe", "Give every track a speaker name.")
                return
        if not llm.provider_ready():
            messagebox.showerror("CampaignScribe", llm.not_ready_message())
            return
        try:
            models.diarization_dir()
        except models.MissingModelError as e:
            messagebox.showerror("CampaignScribe", str(e))
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

        self._run_mode = self.mode_var.get()
        self._cancel.clear()
        self._set_busy(True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            provider = llm.get_provider()
        except llm.LLMError as e:
            self._set_status(str(e))
            self.after(0, lambda: self._set_busy(False))
            return
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
        )

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            if self._run_mode == "tracks":
                self._worker_tracks(provider, speakers_doc, ignored_ids, pipeline, run_ts)
            else:
                self._worker_mixed(provider, speakers_doc, ignored_ids, pipeline, run_ts)
        finally:
            try:
                pipeline.close()
            except Exception:
                pass
            self.after(0, lambda: self._set_busy(False))

    def _worker_mixed(self, provider, speakers_doc, ignored_ids, pipeline, run_ts):
        all_segments: list[dict[str, Any]] = []

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

                count_kwargs = transcriber.diarization_run_kwargs(
                    self._run_params.get("expected_count"),
                    int(self.spk_var.get()),
                )
                segments = pipeline.transcribe_file(wav, progress=progress_cb, **count_kwargs)
                # Save raw JSON
                json_path = os.path.join(self.output_dir, f"transcript_{run_ts}_{i}.json")
                transcriber.save_segments_json(segments, json_path)
                self._add_output(json_path)

                self._set_row(ap, "identifying", f"{provider.display_name} speaker mapping")
                mapping = speaker_id.identify_speakers(segments, speakers_doc, provider)
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

        # persist clusters even on partial/cancelled runs — partial speaker data still helps Review
        if all_segments and self.session_id:
            try:
                self._persist_detected_speakers(self.session_id, all_segments)
            except Exception:
                pass

        self._write_improvements(all_segments, speakers_doc, provider)
        self._update_session_record()
        self._stash_embeddings(getattr(pipeline, "_last_speaker_embeddings", None))

    def _write_improvements(self, all_segments, speakers_doc, provider) -> str:
        """Produce speakers_improvements_*.json after a run. Sets and returns the final status."""
        final = "Done."
        if all_segments and not self._cancel.is_set():
            try:
                self._set_status("Generating speaker improvement suggestions\u2026")
                imp = speaker_id.refine_speakers(all_segments, speakers_doc, provider)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                imp_path = os.path.join(self.output_dir, f"speakers_improvements_{ts}.json")
                with open(imp_path, "w", encoding="utf-8") as f:
                    json.dump(imp, f, indent=2, ensure_ascii=False)
                self._add_output(imp_path)
                final = (
                    "Done. Speaker-improvement suggestions saved \u2014 open the Refine tab "
                    "to review them and fold them into your profile before your "
                    "next session."
                )
            except Exception as e:
                final = f"Done \u2014 improvements step failed: {e}"
        self._set_status(final)
        return final

    def _update_session_record(self, extra: dict | None = None) -> None:
        """Mark the linked session transcribed (best-effort)."""
        if self.session_id:
            try:
                db.update_session(
                    self.session_id,
                    transcripts_folder=self.output_dir,
                    speakers_json_path=self.speakers_path,
                    status="transcribed",
                    **(extra or {}),
                )
            except Exception:
                pass

    def _stash_embeddings(self, emb) -> None:
        """Voice Auto-Match (Spec 2): stash per-cluster embeddings for the session's
        Review step. Best-effort; transcription must never be affected."""
        if config.load_config().get("voice_match_enabled", True) and self.session_id:
            try:
                from app.core import voiceprints

                if emb:
                    voiceprints.stash_session_embeddings(self.session_id, emb)
            except Exception:  # noqa: BLE001 - best-effort
                pass

    def _worker_tracks(self, provider, speakers_doc, ignored_ids, pipeline, run_ts):
        tracks = self._tracks()
        count_kwargs = transcriber.diarization_run_kwargs(
            self._run_params.get("expected_count"), int(self.spk_var.get())
        )

        def progress(i: int, stage: str) -> None:
            if self._cancel.is_set():
                raise InterruptedError("Cancelled")
            path = tracks[i - 1].path
            state = {"converting": "converting", "complete": "complete", "failed": "failed"}.get(
                stage, "transcribing"
            )
            self._set_row(path, state, "" if state != "transcribing" else stage)
            self._set_status(f"[{i}/{len(tracks)}] {os.path.basename(path)} \u2014 {stage}")

        try:
            res = multitrack.transcribe_tracks(
                pipeline,
                tracks,
                wav_for=lambda t: audio.convert_to_wav(t.path),
                shared_mic_count_kwargs=count_kwargs,
                progress=progress,
            )
        except InterruptedError:
            for t in tracks:
                iid = self.row_items.get(t.path)
                if iid is None or not str(self.tree.set(iid, "state")).endswith("complete"):
                    self._set_row(t.path, "failed", "cancelled")
            self._set_status("Cancelled \u2014 nothing written.")
            return

        for path, err in res.failures.items():
            config.log_exception(
                f"transcribe_tab[tracks:{os.path.basename(path)}]", RuntimeError(err)
            )
            self._set_row(path, "failed", err[:100])
        if not res.mapping:
            self._set_status("All tracks failed \u2014 nothing written.")
            return

        json_path = os.path.join(self.output_dir, f"transcript_{run_ts}_tracks.json")
        transcriber.save_segments_json(res.segments, json_path)
        self._add_output(json_path)
        map_path = os.path.join(self.output_dir, f"speaker_mapping_{run_ts}_tracks.json")
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(res.mapping, f, indent=2, ensure_ascii=False)
        self._add_output(map_path)
        txt = speaker_id.format_segments_to_text(res.segments, res.mapping, ignored_ids)
        txt_path = os.path.join(self.output_dir, f"transcript_{run_ts}_tracks.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt)
        self._add_output(txt_path)

        if self.session_id:
            try:
                self._persist_detected_speakers(self.session_id, res.segments, names=res.mapping)
            except Exception:  # noqa: BLE001 - review data is best-effort
                pass

        final = self._write_improvements(res.segments, speakers_doc, provider)
        self._update_session_record(
            extra={"source_audio_files": json.dumps([t.path for t in tracks])}
        )
        self._stash_embeddings(res.embeddings)
        warning = multitrack.duration_mismatch(
            {p: d for p, d in res.durations.items() if p not in res.failures}
        )
        if warning:
            self._set_status(f"{warning}  {final}")

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

    def _persist_detected_speakers(
        self, session_id: int, segments: list, names: dict[str, str] | None = None
    ) -> None:
        """Record the distinct diarized speaker labels from a transcribe run onto
        the session, so the SessionView 'Review speakers' step has real clusters."""
        labels = []
        for seg in segments:
            lab = seg.get("speaker") if isinstance(seg, dict) else getattr(seg, "speaker", None)
            if lab and lab not in labels:
                labels.append(lab)
        db.update_session(session_id, num_speakers_detected=len(labels))
        existing = {r["source_speaker_id"] for r in db.get_speakers_for_session(session_id)}
        for lab in labels:
            if lab not in existing:
                db.add_speaker_profile(
                    session_id,
                    {
                        "source_speaker_id": lab,
                        "display_name": (names or {}).get(lab, ""),
                        "include_in_tracking": 1,
                    },
                )

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
        refine_tab.active_slug = self.active_slug
        refine_tab.speakers_path = self.speakers_path
        try:
            refine_tab.speakers_doc = speakers_io.load_speakers_json(self.speakers_path)
        except Exception:
            pass
        refine_tab.suggestions = doc
        refine_tab._render_suggestions()
        self.app.notebook.select(self.app.refine_tab)
