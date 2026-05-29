"""Speaker Discovery: process a sample, infer speaker profiles, save to DB."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import audio, speaker_id, transcriber
from app.data import db
from app.ui.common import make_readonly, short_path
from app.ui.theme import BTN_ACCENT, LBL_DIM, LBL_HEADER, color


class DiscoverTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.selected_file: str | None = None
        self.session_id: int | None = None
        self._cancel = threading.Event()
        self._busy = False

        cfg = config.load_config()

        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Speaker Discovery", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(self, text="Campaign name:").grid(row=1, column=0, sticky="w", **pad)
        self.campaign_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.campaign_var, width=40).grid(
            row=1, column=1, columnspan=2, sticky="w", **pad
        )

        ttk.Label(self, text="Session label:").grid(row=2, column=0, sticky="w", **pad)
        self.label_var = tk.StringVar(value="Untitled Session")
        ttk.Entry(self, textvariable=self.label_var, width=40).grid(
            row=2, column=1, columnspan=2, sticky="w", **pad
        )

        # Drop zone
        self.drop = tk.Label(
            self,
            text="(no file selected)\nClick Browse to choose a sample audio file\n(.wav .mp3 .m4a .flac .ogg .mp4 .webm)",
            relief="ridge",
            borderwidth=2,
            padx=20,
            pady=24,
            justify="center",
            background=color("BG_INPUT"),
            foreground=color("FG_MUTED"),
            anchor="center",
        )
        self.drop.grid(row=3, column=0, columnspan=4, sticky="ew", **pad)
        self.drop.bind("<Button-1>", lambda _e: self._browse_audio())

        ttk.Button(self, text="Browse audio…", command=self._browse_audio).grid(
            row=4, column=0, sticky="w", **pad
        )
        ttk.Button(self, text="Clear", command=self._clear_audio).grid(
            row=4, column=1, sticky="w", **pad
        )

        ttk.Label(self, text="Expected speakers:").grid(row=5, column=0, sticky="w", **pad)
        self.spk_var = tk.IntVar(value=int(cfg.get("default_num_speakers", 5)))
        ttk.Spinbox(self, from_=1, to=20, textvariable=self.spk_var, width=8).grid(
            row=5, column=1, sticky="w", **pad
        )
        ttk.Label(self, text="Whisper model:").grid(row=5, column=2, sticky="w", **pad)
        self.model_var = tk.StringVar(value=cfg.get("default_whisper_model", "small"))
        ttk.Combobox(
            self,
            textvariable=self.model_var,
            state="readonly",
            width=12,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=5, column=3, sticky="w", **pad)

        self.go_btn = ttk.Button(
            self, text="Analyze Audio & Discover Speakers", style=BTN_ACCENT, command=self._start
        )
        self.go_btn.grid(row=6, column=0, columnspan=4, sticky="ew", **pad)

        self.cancel_btn = ttk.Button(
            self, text="Cancel", command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.grid(row=7, column=0, sticky="w", **pad)

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=1, columnspan=3, sticky="ew", **pad)

        self.status_var = tk.StringVar(value="Waiting for audio file…")
        ttk.Label(self, textvariable=self.status_var, style=LBL_DIM).grid(
            row=8, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(self, text="Results:").grid(row=9, column=0, sticky="nw", **pad)
        self.result = tk.Text(self, height=10, wrap="word")
        self.result.grid(row=9, column=1, columnspan=3, sticky="nsew", **pad)
        make_readonly(self.result)  # selectable/copyable, but not editable

        self.proceed_btn = ttk.Button(
            self,
            text="Proceed to Build Profile",
            command=lambda: self.app.jump_to_tab(1),
            state="disabled",
        )
        self.proceed_btn.grid(row=10, column=0, columnspan=4, sticky="e", **pad)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)
        self.rowconfigure(9, weight=1)

    # ---------- helpers ----------

    def on_settings_changed(self):
        cfg = config.load_config()
        self.spk_var.set(int(cfg.get("default_num_speakers", 5)))
        self.model_var.set(cfg.get("default_whisper_model", "small"))

    def _browse_audio(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Select audio file",
            initialdir=config.get_last_dir("audio") or None,
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm"),
                ("All files", "*.*"),
            ],
        )
        if path:
            config.set_last_dir("audio", path)
            self.selected_file = path
            size_mb = os.path.getsize(path) / 1e6
            self.drop.config(
                text=f"{os.path.basename(path)}\n{size_mb:.1f} MB\n{short_path(path, 70)}"
            )

    def _clear_audio(self):
        if self._busy:
            return
        self.selected_file = None
        self.drop.config(text="(no file selected)\nClick Browse to choose a sample audio file")

    def _set_status(self, msg: str, pct: float = -1.0):
        def apply():
            self.status_var.set(msg)
            if pct >= 0:
                self.progress["value"] = max(0, min(100, pct * 100))

        self.after(0, apply)

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.go_btn.config(state=state)
        self.cancel_btn.config(state="normal" if busy else "disabled")

    def _start(self):
        if self._busy:
            return
        if not self.selected_file:
            messagebox.showerror("CampaignScribe", "Pick an audio file first.")
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
        self.proceed_btn.config(state="disabled")
        self._cancel.clear()
        self._set_busy(True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _cancel_run(self):
        if self._busy:
            self._cancel.set()
            self._set_status("Cancelling… (will stop after current step)")

    def _worker(self):
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        wav_path: str | None = None
        try:
            self._set_status("Converting audio to 16kHz mono WAV…", 0.05)
            wav_path = audio.convert_to_wav(self.selected_file)

            if self._cancel.is_set():
                raise InterruptedError("Cancelled")

            self._set_status("Loading WhisperX models (first run downloads them)…", 0.10)
            pipeline = transcriber.TranscriptionPipeline(
                model_size=self.model_var.get(),
                hf_token=hf,
            )

            def progress_cb(stage: str, pct: float):
                if self._cancel.is_set():
                    raise InterruptedError("Cancelled")
                self._set_status(stage + "…", 0.10 + pct * 0.65)

            segments = pipeline.transcribe_file(
                wav_path,
                num_speakers=int(self.spk_var.get()),
                progress=progress_cb,
            )

            if self._cancel.is_set():
                raise InterruptedError("Cancelled")

            self._set_status("Sending speaker samples to Claude…", 0.85)
            result = speaker_id.discover_speakers(segments, api_key)

            self._set_status("Saving session and speaker profiles…", 0.95)
            session_id = db.create_session(
                display_name=self.label_var.get() or "Untitled Session",
                campaign_name=self.campaign_var.get() or "",
                source_audio_files=[self.selected_file],
            )
            db.update_session(
                session_id,
                num_speakers_detected=int(result.get("num_speakers_detected", 0)),
                status="onboarded",
            )
            for prof in result.get("profiles", []):
                db.add_speaker_profile(
                    session_id,
                    {
                        "source_speaker_id": prof.get("source_speaker_id", ""),
                        "display_name": prof.get("suggested_display_name", ""),
                        "role": (
                            "Dungeon Master"
                            if prof.get("inferred_role", "").upper() == "DM"
                            else (prof.get("inferred_role") or "Player")
                        ),
                        "notes": prof.get("notes", ""),
                        "speech_patterns": prof.get("speech_patterns", []),
                        "sample_quotes": prof.get("sample_quotes", []),
                        "confidence": prof.get("confidence", "medium"),
                        "include_in_tracking": 1,
                    },
                )
            self.session_id = session_id
            self._set_status(f"Done. Session #{session_id} saved.", 1.0)
            self._show_results(result, session_id)
        except InterruptedError:
            self._set_status("Cancelled.", 0.0)
        except Exception as e:
            log_path = config.log_exception("discover_tab.onboard", e)
            self._set_status(f"Error: {e}", 0.0)
            msg = f"{e}\n\nFull traceback written to:\n{log_path}"
            self.after(0, lambda m=msg: messagebox.showerror("CampaignScribe", m))
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            self.after(0, lambda: self._set_busy(False))

    def _show_results(self, result, session_id):
        n = result.get("num_speakers_detected", 0)
        notes = result.get("onboarding_notes", "")
        profiles = result.get("profiles", [])
        text = [f"Detected {n} speaker(s). Session #{session_id} saved.", ""]
        if notes:
            text.append("Notes: " + notes)
            text.append("")
        for p in profiles:
            text.append(
                f"- {p.get('source_speaker_id', '?')} → "
                f"{p.get('suggested_display_name', '?')} "
                f"[{p.get('inferred_role', '?')}, conf={p.get('confidence', '?')}]"
            )
            if p.get("notes"):
                text.append(f"    {p['notes']}")
        text.append("")
        text.append("Open the Build Profile tab to name speakers and save speakers.json.")

        def apply():
            self.result.delete("1.0", "end")
            self.result.insert("1.0", "\n".join(text))
            self.proceed_btn.config(state="normal")

        self.after(0, apply)
