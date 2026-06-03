"""Edit Profile: campaign-scoped, versioned roster editor Toplevel. Replaces Build Profile."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from app import config
from app.core import library, speakers_io
from app.ui.common import ScrollableFrame
from app.ui.speaker_editor import SpeakerEditor
from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, LBL_HEADER, S_2, S_3


class EditProfileWindow(tk.Toplevel):
    def __init__(self, master, app_window, slug: str):
        super().__init__(master)
        self.app = app_window
        self.slug: str | None = None
        self.editors: list[SpeakerEditor] = []
        self.ignored: list[dict[str, Any]] = []  # ignored voices (raw dicts)
        self.npcs: list[dict[str, Any]] = []
        self._busy = False
        self._cancel = threading.Event()

        self.title("Edit Profile")
        self.geometry("760x680")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        pad = {"padx": S_3, "pady": S_2}

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Button(bar, text="◂ Home", style=BTN_GHOST, command=self._back_home).pack(side="left")
        self.title_var = tk.StringVar(value="Edit Profile")
        ttk.Label(bar, textvariable=self.title_var, style=LBL_HEADER).pack(side="left", padx=S_3)
        ttk.Button(
            bar, text="Save as new version", style=BTN_ACCENT, command=self._save_new_version
        ).pack(side="right")
        ttk.Button(bar, text="Export copy…", style=BTN_GHOST, command=self._export).pack(
            side="right", padx=S_2
        )
        ttk.Button(bar, text="Import…", style=BTN_GHOST, command=self._import).pack(side="right")

        ctx_row = ttk.Frame(self)
        ctx_row.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(ctx_row, text="Context (campaign tone, setting):", style=LBL_DIM).pack(anchor="w")
        self.context_box = tk.Text(ctx_row, height=2, wrap="word")
        self.context_box.pack(fill="x")

        tools = ttk.Frame(self)
        tools.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Button(tools, text="＋ Add player", style=BTN_GHOST, command=self._add_player).pack(
            side="left", padx=(0, S_2)
        )
        ttk.Button(
            tools, text="⟲ Discover from audio…", style=BTN_GHOST, command=self._discover_from_audio
        ).pack(side="left", padx=(0, S_2))
        ttk.Button(tools, text="＋ NPC…", style=BTN_GHOST, command=self._add_npc).pack(side="left")
        self.npc_var = tk.StringVar()
        ttk.Label(tools, textvariable=self.npc_var, style=LBL_DIM).pack(side="left", padx=S_3)

        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=3, column=0, sticky="nsew", **pad)

        ver_row = ttk.LabelFrame(self, text="Versions")
        ver_row.grid(row=4, column=0, sticky="ew", **pad)
        self.versions = ttk.Treeview(
            ver_row, columns=("v", "created", "label"), show="headings", height=4
        )
        for c, w in (("v", 60), ("created", 160), ("label", 200)):
            self.versions.heading(c, text=c.title())
            self.versions.column(c, width=w, anchor="w")
        self.versions.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        vbtns = ttk.Frame(ver_row)
        vbtns.pack(side="left", padx=4)
        ttk.Button(vbtns, text="View", style=BTN_GHOST, command=self._view_version).pack(
            fill="x", pady=2
        )
        ttk.Button(vbtns, text="Set current", style=BTN_GHOST, command=self._set_current).pack(
            fill="x", pady=2
        )

        # Load the campaign into the editor (mirrors SessionView ending its
        # __init__ with its render calls). Close/Back is the "◂ Home" button,
        # which destroys this Toplevel.
        self.load_campaign(slug)

    # ---------- load ----------
    def load_campaign(self, slug: str) -> None:
        self.slug = slug
        row = next((r for r in library.list_campaigns() if r["slug"] == slug), None)
        self.title_var.set(f"Edit Profile — {row['display_name'] if row else slug}")
        try:
            doc = library.get_current_doc(slug)
        except FileNotFoundError:
            doc = speakers_io.empty_speakers_doc(row["display_name"] if row else "")
        self.npcs = list(doc.get("npcs", []))
        self.context_box.delete("1.0", "end")
        self.context_box.insert("1.0", doc.get("context", "") or "")
        players = [
            {
                "source_speaker_id": p.get("source_speaker_id", ""),
                "display_name": p.get("player_name", ""),
                "character_name": p.get("character_name", ""),
                "character_class": p.get("character_class", ""),
                "role": p.get("role", "Player"),
                "include_in_tracking": 1,
                "notes": p.get("notes", ""),
                "speech_patterns": p.get("speech_patterns", []),
                "sample_quotes": [],
                "confidence": "high",
            }
            for p in doc.get("players", [])
        ]
        # Split known_non_players by the ignore flag:
        #   ignore=True (or absent)  → truly ignored voice → self.ignored
        #   ignore=False             → tracked Non-Player  → loaded as an editor
        self.ignored = []
        for n in doc.get("known_non_players", []):
            if n.get("ignore", True):
                self.ignored.append(
                    {
                        "source_speaker_id": n.get("source_speaker_id", ""),
                        "display_name": n.get("name", ""),
                        "notes": n.get("notes", ""),
                        "speech_patterns": n.get("speech_patterns", []),
                    }
                )
            else:
                players.append(
                    {
                        "source_speaker_id": n.get("source_speaker_id", ""),
                        "display_name": n.get("name", ""),
                        "character_name": "",
                        "character_class": "",
                        "role": "Non-Player",
                        "include_in_tracking": 1,
                        "notes": n.get("notes", ""),
                        "speech_patterns": n.get("speech_patterns", []),
                        "sample_quotes": [],
                        "confidence": "high",
                    }
                )
        self._render(players)
        self._refresh_npc_label()
        self._refresh_versions()

    def _render(self, players: list[dict[str, Any]]) -> None:
        for w in list(self.scroll.inner.winfo_children()):
            w.destroy()
        self.editors.clear()
        ttk.Label(self.scroll.inner, text="Players & DM", style=LBL_HEADER).pack(
            anchor="w", pady=(4, 2)
        )
        for sp in players:
            ed = SpeakerEditor(self.scroll.inner, sp)
            ed.pack(fill="x", padx=4, pady=4)
            self.editors.append(ed)
        # Ignored voices group
        ttk.Label(self.scroll.inner, text="Ignored voices", style=LBL_DIM).pack(
            anchor="w", pady=(10, 2)
        )
        for i, n in enumerate(self.ignored):
            row = ttk.Frame(self.scroll.inner)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(
                row, text=f"⌀ {n['display_name'] or '(unnamed)'}   IGNORED", style=LBL_DIM
            ).pack(side="left")
            ttk.Button(
                row,
                text="↑ Track as player",
                style=BTN_GHOST,
                command=lambda idx=i: self._promote_ignored(idx),
            ).pack(side="right")

    def _add_player(self) -> None:
        sp = {
            "source_speaker_id": "",
            "display_name": "",
            "role": "Player",
            "include_in_tracking": 1,
        }
        ed = SpeakerEditor(self.scroll.inner, sp)
        ed.pack(fill="x", padx=4, pady=4)
        self.editors.append(ed)

    def _promote_ignored(self, idx: int) -> None:
        n = self.ignored.pop(idx)
        players = [ed.collect() for ed in self.editors]
        players.append(
            {
                "source_speaker_id": n.get("source_speaker_id", ""),
                "display_name": n.get("display_name", ""),
                "character_name": "",
                "character_class": "",
                "role": "Player",
                "include_in_tracking": 1,
                "notes": n.get("notes", ""),
                "speech_patterns": n.get("speech_patterns", []),
                "sample_quotes": [],
                "confidence": "high",
            }
        )
        self._render(players)

    # ---------- NPCs ----------
    def _add_npc(self) -> None:
        name = simpledialog.askstring("Add NPC", "NPC name:", parent=self)
        if not name or not name.strip():
            return
        notes = simpledialog.askstring("Add NPC", "Notes (optional):", parent=self) or ""
        self._add_npc_direct(name.strip(), notes.strip())

    def _add_npc_direct(self, name: str, notes: str) -> None:
        self.npcs.append({"name": name, "notes": notes})
        self._refresh_npc_label()

    def _refresh_npc_label(self) -> None:
        self.npc_var.set(
            "NPCs: " + (", ".join(n["name"] for n in self.npcs) if self.npcs else "(none)")
        )

    # ---------- versions ----------
    def _refresh_versions(self) -> None:
        self.versions.delete(*self.versions.get_children())
        if not self.slug:
            return
        versions = library.list_versions(self.slug)
        cur = next((r["current"] for r in library.list_campaigns() if r["slug"] == self.slug), "")
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

    def _view_version(self) -> None:
        sel = self.versions.selection()
        if not sel or not self.slug:
            return
        from app.ui.common import open_path_native

        open_path_native(str(library.version_path(self.slug, sel[0])))

    def _set_current(self) -> None:
        sel = self.versions.selection()
        if not sel or not self.slug:
            return
        library.set_current(self.slug, sel[0])
        self.load_campaign(self.slug)

    # ---------- save / import / export ----------
    def _build_doc(self) -> dict[str, Any]:
        speakers = [ed.collect() for ed in self.editors]
        speakers += [
            {
                "display_name": n["display_name"],
                "role": "Non-Player",
                "include_in_tracking": 0,
                "notes": n.get("notes", ""),
                "speech_patterns": n.get("speech_patterns", []),
                "source_speaker_id": n.get("source_speaker_id", ""),
            }
            for n in self.ignored
        ]
        row = next((r for r in library.list_campaigns() if r["slug"] == self.slug), None)
        return speakers_io.profiles_to_speakers_doc(
            campaign=row["display_name"] if row else "",
            context=self.context_box.get("1.0", "end").strip(),
            speakers=speakers,
            npcs=self.npcs,
        )

    def _save_new_version(self) -> None:
        if not self.slug:
            return
        library.add_version(self.slug, self._build_doc())
        self._refresh_versions()
        self.after(0, lambda: messagebox.showinfo("CampaignScribe", "Saved a new profile version."))

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="Import speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path or not self.slug:
            return
        try:
            doc = speakers_io.load_speakers_json(path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
        config.set_last_dir("json", path)
        library.add_version(self.slug, doc, label="imported")
        self.load_campaign(self.slug)

    def _export(self) -> None:
        if not self.slug:
            return
        dest = filedialog.asksaveasfilename(
            title="Export copy…",
            defaultextension=".json",
            initialfile="speakers.json",
            initialdir=config.get_last_dir("json") or None,
            filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        speakers_io.save_speakers_json(dest, self._build_doc())
        config.set_last_dir("json", dest)
        messagebox.showinfo("CampaignScribe", f"Exported to {dest}")

    def _back_home(self) -> None:
        self.destroy()
        if hasattr(self.app, "open_home"):
            self.app.open_home()

    # ---------- discover from audio ----------
    def _discover_from_audio(self, path: str | None = None) -> None:
        # Reuses the diarization + Claude profiling worker (formerly in the
        # retired Discover tab): convert -> TranscriptionPipeline.transcribe_file ->
        # speaker_id.discover_speakers, then APPEND the returned profiles to the
        # editor list (no DB session is created here — this only seeds the roster).
        from app.core import audio, speaker_id, transcriber

        if path is None:
            path = filedialog.askopenfilename(
                title="Discover speakers from audio",
                initialdir=config.get_last_dir("audio") or None,
                filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm")],
            )
        if not path:
            return
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        if not api_key or not hf:
            messagebox.showerror(
                "CampaignScribe",
                "Discover needs an Anthropic API key and a HuggingFace token (Settings ⚙).",
            )
            return
        config.set_last_dir("audio", path)
        self.npc_var.set("Discovering speakers from audio…")

        def worker() -> None:
            wav = None
            try:
                wav = audio.convert_to_wav(path)
                pipeline = transcriber.TranscriptionPipeline(
                    model_size=config.load_config().get("default_whisper_model", "small"),
                    hf_token=hf,
                )
                try:
                    segments = pipeline.transcribe_file(
                        wav,
                        num_speakers=int(config.load_config().get("default_num_speakers", 5)),
                    )
                    result = speaker_id.discover_speakers(segments, api_key)
                finally:
                    try:
                        pipeline.close()
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001 - surfaced to the user below
                config.log_exception("edit_profile.discover", e)
                self.after(0, lambda msg=str(e): messagebox.showerror("CampaignScribe", msg))
                return
            finally:
                import os

                if wav and os.path.exists(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass

            def apply() -> None:
                for prof in result.get("profiles", []):
                    sp = {
                        "source_speaker_id": prof.get("source_speaker_id", ""),
                        "display_name": prof.get("suggested_display_name", ""),
                        "role": (
                            "Dungeon Master"
                            if prof.get("inferred_role", "").upper() == "DM"
                            else (prof.get("inferred_role") or "Player")
                        ),
                        "include_in_tracking": 1,
                        "notes": prof.get("notes", ""),
                        "speech_patterns": prof.get("speech_patterns", []),
                        "sample_quotes": prof.get("sample_quotes", []),
                        "confidence": prof.get("confidence", "medium"),
                    }
                    ed = SpeakerEditor(self.scroll.inner, sp)
                    ed.pack(fill="x", padx=4, pady=4)
                    self.editors.append(ed)
                self._refresh_npc_label()

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def start_discover(self, audio_path: str) -> None:
        """Kick off speaker discovery on a specific audio file (used by the
        Transcribe cold-start on-ramp). Opens nothing; runs Discover on `audio_path`."""
        self._discover_from_audio(path=audio_path)
