"""Session detail Toplevel: header, audio, pipeline stepper, ① confirm, ② review."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import library, speakers_io
from app.data import db
from app.ui.common import ScrollableFrame
from app.ui.theme import BTN_ACCENT, BTN_GHOST, LBL_DIM, S_2, S_3

try:
    from app.core import voiceprints as _voiceprints
except Exception:  # pragma: no cover — import fails only when numpy absent
    _voiceprints = None  # type: ignore[assignment]

IGNORE_CHOICE = "__ignore__"
GUEST_CHOICE = "__guest__"


class SessionView(tk.Toplevel):
    def __init__(self, master, app_window, session_id: int):
        super().__init__(master)
        self.app = app_window
        self.session_id = session_id
        self.session = db.get_session(session_id) or {}
        self.slug = self.session.get("campaign_slug")
        self._roster: list[str] = []  # tracked player names from the profile
        self._absent: set[str] = set()  # names marked absent tonight
        self._guests: list[str] = []  # extra expected guests
        self._assignments: dict[str, str] = {}  # cluster id -> roster name / guest / __ignore__

        self.title(f"Session — {self.session.get('display_name', 'Untitled')}")
        self.geometry("760x640")
        self.minsize(640, 520)
        pad = {"padx": S_3, "pady": S_2}

        self._scroll = ScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True)
        body = self._scroll.inner

        bar = ttk.Frame(body)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="◂ Home", style=BTN_GHOST, command=self._back_home).pack(side="left")
        self.name_var = tk.StringVar(value=self.session.get("display_name", ""))
        ttk.Entry(bar, textvariable=self.name_var, width=40).pack(side="left", padx=S_3)
        ttk.Button(bar, text="Rename", style=BTN_GHOST, command=self._rename).pack(side="left")
        self.status_var = tk.StringVar(value=self.session.get("status", "new"))
        ttk.Label(bar, textvariable=self.status_var, style=LBL_DIM).pack(side="right")

        # Audio
        audio_lf = ttk.LabelFrame(body, text="Audio")
        audio_lf.pack(fill="x", **pad)
        self.audio_box = tk.Listbox(audio_lf, height=3)
        self.audio_box.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        ttk.Button(audio_lf, text="＋ add track", style=BTN_GHOST, command=self._add_track).pack(
            side="left", padx=4
        )
        for f in json.loads(self.session.get("source_audio_files") or "[]"):
            self.audio_box.insert("end", f)

        # ① Confirm who's here
        confirm_lf = ttk.LabelFrame(body, text="① Confirm who's here")
        confirm_lf.pack(fill="x", **pad)
        self.confirm_inner = ttk.Frame(confirm_lf)
        self.confirm_inner.pack(fill="x", padx=4, pady=4)
        self.count_var = tk.StringVar()
        ttk.Label(confirm_lf, textvariable=self.count_var, style=LBL_DIM).pack(anchor="w", padx=4)
        countrow = ttk.Frame(confirm_lf)
        countrow.pack(fill="x", padx=4, pady=2)
        ttk.Label(countrow, text="Expected voices for this run:").pack(side="left")
        self.count_spin_var = tk.IntVar(value=0)
        self._count_auto_value = 0
        ttk.Spinbox(countrow, from_=1, to=20, textvariable=self.count_spin_var, width=6).pack(
            side="left", padx=6
        )
        crow = ttk.Frame(confirm_lf)
        crow.pack(fill="x", padx=4, pady=4)
        ttk.Button(crow, text="＋ add guest", style=BTN_GHOST, command=self._add_guest_dialog).pack(
            side="left"
        )
        ttk.Button(
            crow,
            text="Start transcription ▸",
            style=BTN_ACCENT,
            command=self._start_transcription,
        ).pack(side="right")

        # ② Review speakers
        review_lf = ttk.LabelFrame(body, text="② Review speakers")
        review_lf.pack(fill="both", expand=True, **pad)
        self.review_inner = ttk.Frame(review_lf)
        self.review_inner.pack(fill="both", expand=True, padx=4, pady=4)
        rrow = ttk.Frame(review_lf)
        rrow.pack(fill="x", padx=4, pady=4)
        ttk.Button(
            rrow,
            text="Save changes to profile ▸",
            style=BTN_GHOST,
            command=self._save_to_profile,
        ).pack(side="right")

        self._load_roster()
        self._render_confirm()
        self._render_review()

    # ---------- roster / ① ----------

    def _load_roster(self) -> None:
        self._roster = []
        if not self.slug:
            return
        try:
            doc = library.get_current_doc(self.slug)
        except Exception:
            return
        self._roster = [
            p.get("player_name", "") for p in doc.get("players", []) if p.get("player_name")
        ]

    def _render_confirm(self) -> None:
        for w in list(self.confirm_inner.winfo_children()):
            w.destroy()
        self._absent_vars: dict[str, tk.BooleanVar] = {}
        for name in self._roster + self._guests:
            var = tk.BooleanVar(value=name not in self._absent)
            self._absent_vars[name] = var
            ttk.Checkbutton(
                self.confirm_inner,
                text=name,
                variable=var,
                command=lambda n=name: self._toggle_present(n),
            ).pack(anchor="w")
        self._update_count()

    def _toggle_present(self, name: str) -> None:
        if self._absent_vars[name].get():
            self._absent.discard(name)
        else:
            self._absent.add(name)
        self._update_count()

    def mark_absent(self, name: str) -> None:
        self._absent.add(name)
        self._render_confirm()

    def add_guest(self, name: str) -> None:
        self._guests.append(name)
        self._render_confirm()
        self._render_review()

    def _add_guest_dialog(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add guest", "Guest name:", parent=self)
        if name and name.strip():
            self.add_guest(name.strip())

    def _update_count(self) -> None:
        n = self.expected_speaker_count()
        self.count_var.set(f"Present in roster: {n}")
        if hasattr(self, "count_spin_var"):
            # Auto-follow the roster tally until the user overrides the spinbox;
            # once they set a different number, respect it (don't clobber on later toggles).
            try:
                current = int(self.count_spin_var.get())
            except Exception:
                current = self._count_auto_value
            if current == self._count_auto_value:
                self.count_spin_var.set(n)
            self._count_auto_value = n

    def expected_speaker_count(self) -> int:
        present = [n for n in (self._roster + self._guests) if n not in self._absent]
        return len(present)

    def _run_params_for_transcribe(self) -> dict:
        try:
            n = int(self.count_spin_var.get())
        except Exception:
            n = self.expected_speaker_count()
        return {"expected_count": max(0, n)}

    # ---------- ② review ----------

    def _detected_clusters(self) -> list[str]:
        rows = db.get_speakers_for_session(self.session_id)
        if rows:
            return [r["source_speaker_id"] for r in rows if r.get("source_speaker_id")]
        n = self.session.get("num_speakers_detected") or 0
        return [f"SPEAKER_{i:02d}" for i in range(int(n))]

    def _render_review(self) -> None:
        for w in list(self.review_inner.winfo_children()):
            w.destroy()
        choices = [c for c in (self._roster + self._guests) if c not in self._absent]
        options = choices + [GUEST_CHOICE, IGNORE_CHOICE]
        self._review_vars: dict[str, tk.StringVar] = {}
        self._chip_labels: dict[str, ttk.Label] = {}
        for cid in self._detected_clusters():
            row = ttk.Frame(self.review_inner)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=cid, width=16).pack(side="left")
            var = tk.StringVar(value=self._assignments.get(cid, ""))
            self._review_vars[cid] = var
            ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=30).pack(
                side="left"
            )
            chip = ttk.Label(row, text="", style=LBL_DIM)
            chip.pack(side="left", padx=(S_2, 0))
            self._chip_labels[cid] = chip
        self._prefill_from_voicematch()

    def assign_cluster(self, cluster_id: str, target: str) -> None:
        self._assignments[cluster_id] = target
        if hasattr(self, "_review_vars") and cluster_id in self._review_vars:
            self._review_vars[cluster_id].set(target)

    def _prefill_from_voicematch(self) -> None:
        """Pre-fill ② cluster assignments from voice fingerprint matches.

        Reads stashed embeddings (peek, not pop — preserved for the learning
        loop in _save_session_mapping) and pre-sets each cluster's StringVar
        to the matched roster person when the cosine score meets the threshold.
        A confidence chip label is updated for every cluster regardless.
        Best-effort: any exception leaves ② exactly as the manual flow would.
        """
        self._cluster_embeddings: dict = {}
        self._match_scores: dict = {}
        try:
            if _voiceprints is None or not self.slug:
                return
            cfg = config.load_config()
            if not cfg.get("voice_match_enabled", True):
                return
            emb = _voiceprints.peek_session_embeddings(self.session_id)
            if not emb:
                return
            self._cluster_embeddings = emb
            threshold = float(cfg.get("voice_match_threshold", 0.70))
            results = _voiceprints.match(self.slug, emb, threshold)
            for cid, (person, score) in results.items():
                self._match_scores[cid] = (person, score)
                if person and score >= threshold:
                    # Pre-set via assign_cluster so both _assignments and the
                    # StringVar are updated — identical state to a manual pick.
                    var = self._review_vars.get(cid)
                    if var is not None and not var.get():
                        self.assign_cluster(cid, person)
                # Update confidence chip label for this cluster row.
                lbl = self._chip_labels.get(cid)
                if lbl is not None:
                    if person:
                        lbl.config(text=f"{person} · {score:.2f}")
                    else:
                        lbl.config(text=f"~ {score:.2f}" if score > 0.0 else "no match")
        except Exception:
            pass  # Never crash ② — degrade to manual silently

    def _collect_assignments(self) -> dict[str, str]:
        # Live combobox StringVar wins over programmatic assign_cluster values —
        # if the user changes the combobox after assign_cluster was called, the
        # GUI StringVar is the authoritative value.
        out = dict(self._assignments)
        for cid, var in getattr(self, "_review_vars", {}).items():
            if var.get():
                out[cid] = var.get()
        return out

    def _save_session_mapping(self) -> None:
        db.delete_speakers_for_session(self.session_id)
        for cid, target in self._collect_assignments().items():
            ignore = target == IGNORE_CHOICE
            # GUEST and IGNORE assignments persist with empty display_name —
            # these are session-local and excluded from promote (see D3).
            name = "" if target in (IGNORE_CHOICE, GUEST_CHOICE) else target
            db.add_speaker_profile(
                self.session_id,
                {
                    "source_speaker_id": cid,
                    "display_name": name,
                    "role": "Non-Player" if ignore else "Player",
                    "include_in_tracking": 0 if ignore else 1,
                },
            )

        # Voice Auto-Match (Spec 2): learn from confirmations — feed each confirmed
        # (cluster -> roster person) embedding into that person's fingerprint. Best-effort.
        try:
            cfg = config.load_config()
            if cfg.get("voice_match_enabled", True) and self.slug and _voiceprints is not None:
                emb_map = (
                    getattr(self, "_cluster_embeddings", {})
                    or _voiceprints.peek_session_embeddings(self.session_id)
                    or {}
                )
                roster = set(self._roster)  # real campaign persons only; guests excluded
                for cid, target in self._collect_assignments().items():
                    if not target or target in (IGNORE_CHOICE, GUEST_CHOICE):
                        continue
                    if target in roster and cid in emb_map:
                        _voiceprints.update(self.slug, target, emb_map[cid])
                _voiceprints.pop_session_embeddings(self.session_id)  # consume once learned
        except Exception:  # noqa: BLE001 — learning is best-effort; never block saving
            pass

    def _save_to_profile(self) -> None:
        self._save_session_mapping()
        if not self.slug:
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "CampaignScribe", "This loose session has no campaign to update."
                ),
            )
            return

        # Load the current campaign doc; treat a missing doc as an empty one.
        try:
            cur = library.get_current_doc(self.slug)
        except FileNotFoundError:
            session = db.get_session(self.session_id) or {}
            cur = speakers_io.empty_speakers_doc(session.get("display_name", ""))

        campaign = cur.get("campaign", "")
        context = cur.get("context", "")
        npcs = cur.get("npcs", [])

        # Promote folds session assignments into the existing roster; never drops
        # absent players; guests stay session-local (D3).
        #
        # Step 1 — seed from the EXISTING roster so nobody is silently dropped.
        speakers: list[dict] = []
        for p in cur.get("players", []):
            speakers.append(
                {
                    "display_name": p.get("player_name", ""),
                    "role": p.get("role", "Player"),
                    "character_name": p.get("character_name", ""),
                    "character_class": p.get("character_class", ""),
                    "notes": p.get("notes", ""),
                    "speech_patterns": p.get("speech_patterns", []),
                    "source_speaker_id": p.get("source_speaker_id", ""),
                    "include_in_tracking": 1,
                }
            )
        for n in cur.get("known_non_players", []):
            speakers.append(
                {
                    "display_name": n.get("name", ""),
                    "role": "Non-Player",
                    "notes": n.get("notes", ""),
                    "speech_patterns": n.get("speech_patterns", []),
                    "source_speaker_id": n.get("source_speaker_id", ""),
                    "include_in_tracking": 0 if n.get("ignore", True) else 1,
                }
            )

        # Step 2 — fold in this session's assignments without dropping anyone.
        # GUEST and IGNORE targets have empty display_name in the DB; skip them.
        existing_names = {s["display_name"].casefold() for s in speakers if s["display_name"]}
        rows = db.get_speakers_for_session(self.session_id)
        for r in rows:
            target = r.get("display_name", "")
            if not target:
                # Empty display_name means GUEST or IGNORE — session-local, not promoted.
                continue
            if target.casefold() not in existing_names:
                speakers.append(
                    {
                        "display_name": target,
                        "role": r.get("role", "Player"),
                        "character_name": "",
                        "character_class": "",
                        "notes": r.get("notes", ""),
                        "speech_patterns": [],
                        "source_speaker_id": r.get("source_speaker_id", ""),
                        "include_in_tracking": r.get("include_in_tracking", 1),
                    }
                )
                existing_names.add(target.casefold())

        new_doc = speakers_io.profiles_to_speakers_doc(campaign, context, speakers, npcs=npcs)
        library.add_version(self.slug, new_doc, label="from session")
        self.after(
            0,
            lambda: messagebox.showinfo("CampaignScribe", "Saved changes to the campaign profile."),
        )

    # ---------- misc ----------

    def _add_track(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add audio track(s)",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.webm")],
        )
        if not paths:
            return
        existing = json.loads(self.session.get("source_audio_files") or "[]")
        for p in paths:
            if p not in existing:
                existing.append(p)
                self.audio_box.insert("end", p)
        db.update_session(self.session_id, source_audio_files=json.dumps(existing))
        self.session["source_audio_files"] = json.dumps(existing)

    def _rename(self) -> None:
        new = self.name_var.get().strip()
        if new:
            db.update_session(self.session_id, display_name=new)
            self.title(f"Session — {new}")

    def _start_transcription(self) -> None:
        self._save_session_mapping()
        if hasattr(self.app, "open_session_stage"):
            self.app.open_session_stage(
                self.session_id, "transcribe", run_params=self._run_params_for_transcribe()
            )

    def _back_home(self) -> None:
        self.destroy()
        if hasattr(self.app, "open_home"):
            self.app.open_home()
