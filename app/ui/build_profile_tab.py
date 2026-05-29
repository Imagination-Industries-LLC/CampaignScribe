"""Speaker Profile Builder: name speakers and save speakers.json."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from app import config
from app.core import speakers_io
from app.data import db
from app.ui.common import ScrollableFrame
from app.ui.theme import LBL_HEADER

ROLE_OPTIONS = ["Dungeon Master", "Player", "Non-Player", "Unknown"]


class SpeakerEditor(ttk.LabelFrame):
    """Editable form block for a single speaker."""

    def __init__(self, master, profile: dict[str, Any]):
        sid = profile.get("source_speaker_id", "?")
        title = f"{sid}"
        super().__init__(master, text=title)
        self.profile = dict(profile)
        self.include_var = tk.BooleanVar(value=bool(profile.get("include_in_tracking", 1)))
        self.name_var = tk.StringVar(value=profile.get("display_name", ""))
        self.char_var = tk.StringVar(value=profile.get("character_name", "") or "")
        self.class_var = tk.StringVar(value=profile.get("character_class", "") or "")
        self.role_var = tk.StringVar(value=profile.get("role") or "Player")
        self.notes_var = tk.StringVar(value=profile.get("notes", "") or "")
        self.confidence = profile.get("confidence", "medium")

        pad = {"padx": 6, "pady": 2}
        ttk.Checkbutton(self, text="Include", variable=self.include_var).grid(
            row=0, column=0, sticky="w", **pad
        )
        ttk.Label(self, text=f"Confidence: {self.confidence}").grid(
            row=0, column=1, sticky="w", **pad
        )
        ttk.Label(self, text="Display name:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.name_var, width=28).grid(
            row=1, column=1, sticky="w", **pad
        )
        ttk.Label(self, text="Role:").grid(row=1, column=2, sticky="w", **pad)
        ttk.Combobox(
            self, textvariable=self.role_var, state="readonly", values=ROLE_OPTIONS, width=18
        ).grid(row=1, column=3, sticky="w", **pad)
        ttk.Label(self, text="Character name:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.char_var, width=28).grid(
            row=2, column=1, sticky="w", **pad
        )
        ttk.Label(self, text="Character class:").grid(row=2, column=2, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.class_var, width=20).grid(
            row=2, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Notes:").grid(row=3, column=0, sticky="nw", **pad)
        self.notes_box = tk.Text(self, height=2, width=70, wrap="word")
        self.notes_box.insert("1.0", profile.get("notes", "") or "")
        self.notes_box.grid(row=3, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(self, text="Speech patterns:").grid(row=4, column=0, sticky="nw", **pad)
        self.patterns_box = tk.Text(self, height=4, width=70, wrap="word")
        self.patterns_box.insert("1.0", "\n".join(profile.get("speech_patterns") or []))
        self.patterns_box.grid(row=4, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(self, text="Sample quotes:").grid(row=5, column=0, sticky="nw", **pad)
        self.quotes_box = tk.Text(self, height=3, width=70, wrap="word")
        self.quotes_box.insert("1.0", "\n".join(profile.get("sample_quotes") or []))
        self.quotes_box.grid(row=5, column=1, columnspan=3, sticky="ew", **pad)

        for col in (1, 3):
            self.columnconfigure(col, weight=1)

    def collect(self) -> dict[str, Any]:
        patterns = [
            ln.strip() for ln in self.patterns_box.get("1.0", "end").splitlines() if ln.strip()
        ]
        quotes = [ln.strip() for ln in self.quotes_box.get("1.0", "end").splitlines() if ln.strip()]
        notes = self.notes_box.get("1.0", "end").strip()
        return {
            "source_speaker_id": self.profile.get("source_speaker_id", ""),
            "display_name": self.name_var.get().strip(),
            "character_name": self.char_var.get().strip(),
            "character_class": self.class_var.get().strip(),
            "role": self.role_var.get(),
            "include_in_tracking": 1 if self.include_var.get() else 0,
            "notes": notes,
            "speech_patterns": patterns,
            "sample_quotes": quotes,
            "confidence": self.profile.get("confidence", "medium"),
        }


class BuildProfileTab(ttk.Frame):
    def __init__(self, master, app_window):
        super().__init__(master)
        self.app = app_window
        self.session_id: int | None = None
        self.editors: list[SpeakerEditor] = []
        self.loaded_doc: dict[str, Any] | None = None
        self.loaded_path: str | None = None

        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Speaker Profile Builder", style=LBL_HEADER).grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )

        ttk.Label(self, text="Session:").grid(row=1, column=0, sticky="w", **pad)
        self.session_combo = ttk.Combobox(self, state="readonly", width=60)
        self.session_combo.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Button(self, text="Load Session", command=self._load_session).grid(
            row=1, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="— OR — speakers.json:").grid(row=2, column=0, sticky="w", **pad)
        self.speakers_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.speakers_var, width=60, state="readonly").grid(
            row=2, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._load_existing).grid(
            row=2, column=3, sticky="w", **pad
        )

        ttk.Label(self, text="Campaign:").grid(row=3, column=0, sticky="w", **pad)
        self.campaign_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.campaign_var, width=40).grid(
            row=3, column=1, sticky="w", **pad
        )
        ttk.Label(self, text="Context (campaign tone, setting, etc.):").grid(
            row=4, column=0, sticky="nw", **pad
        )
        self.context_box = tk.Text(self, height=3, wrap="word")
        self.context_box.grid(row=4, column=1, columnspan=3, sticky="ew", **pad)

        # Scrollable speakers
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=5, column=0, columnspan=4, sticky="nsew", **pad)

        ttk.Label(self, text="Output speakers.json:").grid(row=6, column=0, sticky="w", **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.out_var, width=60).grid(
            row=6, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse…", command=self._browse_out).grid(
            row=6, column=3, sticky="w", **pad
        )

        btn_row = ttk.Frame(self)
        btn_row.grid(row=7, column=0, columnspan=4, sticky="e", **pad)
        ttk.Button(btn_row, text="Save speakers.json", command=self._save).pack(side="left", padx=4)
        ttk.Button(
            btn_row,
            text="→ Save & Use in Transcribe",
            command=self._save_and_use_in_transcribe,
        ).pack(side="left", padx=4)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(5, weight=1)

        self.refresh_sessions()

    def on_settings_changed(self):
        pass

    def on_show(self):
        self.refresh_sessions()

    def refresh_sessions(self):
        sessions = db.list_sessions()
        items = []
        self._session_index: list[int] = []
        for s in sessions:
            items.append(
                f"#{s['id']} — {s['display_name']} ({s.get('campaign_name') or 'no campaign'}) "
                f"[{s.get('status', '?')}]"
            )
            self._session_index.append(s["id"])
        self.session_combo["values"] = items

    def _load_session(self):
        idx = self.session_combo.current()
        if idx < 0:
            messagebox.showinfo("CampaignScribe", "Pick a session from the dropdown.")
            return
        sid = self._session_index[idx]
        self.session_id = sid
        sess = db.get_session(sid) or {}
        self.campaign_var.set(sess.get("campaign_name") or "")
        speakers = db.get_speakers_for_session(sid)
        self._render(speakers)
        if not self.out_var.get():
            cfg = config.load_config()
            base = cfg.get("default_output_folder") or str(Path.home() / "CampaignScribe")
            self.out_var.set(str(Path(base) / f"speakers_{sid}.json"))

    def _load_existing(self):
        path = filedialog.askopenfilename(
            title="Select existing speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        config.set_last_dir("json", path)
        try:
            doc = speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        self.loaded_doc = doc
        self.loaded_path = path
        self.speakers_var.set(path)
        self.out_var.set(path)
        self.campaign_var.set(doc.get("campaign", "") or "")
        self.context_box.delete("1.0", "end")
        self.context_box.insert("1.0", doc.get("context", "") or "")
        speakers: list[dict[str, Any]] = []
        for p in doc.get("players", []):
            speakers.append(
                {
                    "source_speaker_id": p.get("source_speaker_id", ""),
                    "display_name": p.get("player_name", ""),
                    "character_name": p.get("character_name", ""),
                    "character_class": p.get("character_class", ""),
                    "role": p.get("role", "Player"),
                    "include_in_tracking": 1,
                    "notes": p.get("notes", ""),
                    "speech_patterns": p.get("speech_patterns", []),
                    "sample_quotes": p.get("sample_quotes", []),
                    "confidence": "high",
                }
            )
        for n in doc.get("known_non_players", []):
            speakers.append(
                {
                    "source_speaker_id": n.get("source_speaker_id", ""),
                    "display_name": n.get("name", ""),
                    "character_name": "",
                    "character_class": "",
                    "role": "Non-Player",
                    "include_in_tracking": 0,
                    "notes": n.get("notes", ""),
                    "speech_patterns": n.get("speech_patterns", []),
                    "sample_quotes": [],
                    "confidence": "high",
                }
            )
        self._render(speakers)

    def _render(self, speakers: list[dict[str, Any]]):
        for w in list(self.scroll.inner.winfo_children()):
            w.destroy()
        self.editors.clear()
        for sp in speakers:
            ed = SpeakerEditor(self.scroll.inner, sp)
            ed.pack(fill="x", padx=4, pady=6)
            self.editors.append(ed)
        if not speakers:
            ttk.Label(
                self.scroll.inner,
                text="(No speakers loaded yet — load a session or speakers.json above.)",
            ).pack(padx=10, pady=20)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            title="Save speakers.json as…",
            defaultextension=".json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json")],
            initialfile="speakers.json",
        )
        if path:
            config.set_last_dir("json", path)
            self.out_var.set(path)

    def _save(self, show_success: bool = True) -> bool:
        if not self.editors:
            messagebox.showerror(
                "CampaignScribe", "Nothing to save — load a session or speakers.json."
            )
            return False
        out_path = self.out_var.get().strip()
        if not out_path:
            messagebox.showerror("CampaignScribe", "Choose an output path.")
            return False
        speakers = [ed.collect() for ed in self.editors]
        for sp in speakers:
            if sp["include_in_tracking"] and not sp["display_name"]:
                messagebox.showerror(
                    "CampaignScribe",
                    f"Speaker {sp.get('source_speaker_id', '?')} is included but has no display name.",
                )
                return False
        doc = speakers_io.profiles_to_speakers_doc(
            campaign=self.campaign_var.get().strip(),
            context=self.context_box.get("1.0", "end").strip(),
            speakers=speakers,
        )
        try:
            speakers_io.save_speakers_json(out_path, doc)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Save failed:\n{e}")
            return False

        # Persist edits back to DB if linked to a session
        if self.session_id:
            existing = db.get_speakers_for_session(self.session_id)
            for sp in speakers:
                match = next(
                    (e for e in existing if e["source_speaker_id"] == sp["source_speaker_id"]),
                    None,
                )
                if match:
                    db.update_speaker_profile(
                        match["id"],
                        display_name=sp["display_name"],
                        character_name=sp["character_name"],
                        character_class=sp["character_class"],
                        role=sp["role"],
                        include_in_tracking=sp["include_in_tracking"],
                        notes=sp["notes"],
                        speech_patterns=sp["speech_patterns"],
                        sample_quotes=sp["sample_quotes"],
                    )
                else:
                    db.add_speaker_profile(self.session_id, sp)
            db.update_session(
                self.session_id,
                speakers_json_path=out_path,
                campaign_name=self.campaign_var.get().strip(),
            )

        cfg = config.load_config()
        cfg["last_speakers_json"] = out_path
        config.save_config(cfg)

        if show_success:
            messagebox.showinfo("CampaignScribe", f"Saved {out_path}")
        return True

    def _save_and_use_in_transcribe(self):
        if not self._save(show_success=False):
            return
        out_path = self.out_var.get().strip()
        transcribe_tab = self.app.transcribe_tab
        transcribe_tab.speakers_var.set(out_path)
        transcribe_tab.speakers_path = out_path
        self.app.jump_to_tab(2)
