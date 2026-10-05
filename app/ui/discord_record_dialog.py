"""Record a session from a Discord voice channel (consent, auto-join, picker, live panel)."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from app import config
from app.core import discord_recorder
from app.core.autostop import autostop_text, fmt_hm, fmt_hms
from app.core.discord_recorder import RecorderError, RecorderProcess, RecorderUnavailable
from app.data import db
from app.ui.common import add_tooltip
from app.ui.theme import (
    BTN_ACCENT,
    BTN_DANGER,
    BTN_GHOST,
    LBL_DIM,
    LBL_STATUS_ERR,
    LBL_STATUS_WARN,
    S_2,
    S_3,
)

CONSENT_TEXT = (
    "Everyone in the voice channel will be recorded. You are responsible for telling "
    "participants and getting their consent where the law requires it. The bot will post "
    "this notice in the channel:"
)
AUTO_STOPPED_TEXT = "Stopped automatically at the maximum recording length."
MAX_EXIT_DEFERRALS = 10  # x300 ms: stop waiting for the reader after ~3 s
LOW_DISK_BYTES = 2 * 1024**3
DOT_HOLD_S = 2.0
_STYLES = {"normal": LBL_DIM, "warn": LBL_STATUS_WARN, "error": LBL_STATUS_ERR}


def attach_wavs_to_db(session_id: int, wavs: list[str]) -> bool:
    """Append wavs (unique) to the session's source_audio_files. False if the session is gone."""
    session = db.get_session(session_id)
    if not session:
        return False
    existing = json.loads(session.get("source_audio_files") or "[]")
    for p in wavs:
        if p not in existing:
            existing.append(p)
    db.update_session(session_id, source_audio_files=json.dumps(existing))
    return True


def _spawn_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class DiscordRecordDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        app,
        session_id: int,
        *,
        session_view=None,
        now: Callable[[], float] = time.monotonic,
        recorder_factory=RecorderProcess,
        spawn: Callable[[Callable[[], None]], None] = _spawn_thread,
    ):
        super().__init__(master)
        self.app = app
        self._session_view = session_view
        self.session_id = session_id
        self._now = now
        self._factory = recorder_factory
        self._spawn = spawn

        self.state = "consent"
        self.recorder = None
        self.out_dir = ""
        self._gen = 0
        self._stopping = False
        self._started_at: float | None = None
        self._tick_id: str | None = None
        self._suspended_for_limit: int | None = None
        self._last_limit: int | None = None
        self._error_msg = ""
        self._last_error_msg = ""
        self._inventory: dict = {}
        self._rows: dict[str, dict] = {}
        self._last_speak: dict[str, float] = {}
        self.autostop_text_value = ""
        self.autostop_style = "normal"

        self.title("Record from Discord")
        self.geometry("460x440")
        self.minsize(400, 340)
        try:
            self.transient(master)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            app.discord_recorder_dialog = self
        except AttributeError:
            pass

        pad = {"padx": S_3, "pady": S_2}
        self._body = ttk.Frame(self)
        self._body.pack(fill="both", expand=True)
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, style=LBL_DIM, wraplength=420).pack(
            side="bottom", fill="x", **pad
        )

        # consent
        self._consent = ttk.Frame(self._body)
        notice = config.load_config().get("discord_notice", "")
        self.consent_label = ttk.Label(
            self._consent, text=f"{CONSENT_TEXT}\n\n{notice}", wraplength=420, justify="left"
        )
        self.consent_label.pack(fill="x", **pad)
        row = ttk.Frame(self._consent)
        row.pack(fill="x", **pad)
        self.start_btn = ttk.Button(
            row, text="Start recording", style=BTN_ACCENT, command=self._start_auto
        )
        self.start_btn.pack(side="right")
        self.cancel_btn = ttk.Button(row, text="Cancel", style=BTN_GHOST, command=self.destroy)
        self.cancel_btn.pack(side="right", padx=S_2)

        # picker
        self._picker = ttk.Frame(self._body)
        ttk.Label(
            self._picker,
            text="You're not in a voice channel the bot can see. Pick one to record:",
            wraplength=420,
        ).pack(anchor="w", **pad)
        self.guild_combo = ttk.Combobox(self._picker, state="readonly")
        self.guild_combo.pack(fill="x", **pad)
        self.guild_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_guild_selected())
        self.channel_combo = ttk.Combobox(self._picker, state="readonly")
        self.channel_combo.pack(fill="x", **pad)
        self.picker_start_btn = ttk.Button(
            self._picker, text="Start recording", style=BTN_ACCENT, command=self._start_picked
        )
        self.picker_start_btn.pack(anchor="e", **pad)

        # live
        self._live = ttk.Frame(self._body)
        self.elapsed_var = tk.StringVar(value="0:00:00")
        ttk.Label(self._live, textvariable=self.elapsed_var, font=("TkDefaultFont", 20)).pack(
            anchor="w", **pad
        )
        self.autostop_label = ttk.Label(self._live, text="", cursor="hand2", style=LBL_DIM)
        self.autostop_label.pack(anchor="w", **pad)
        self.autostop_label.bind("<Button-1>", lambda _e: self._open_limit_settings())
        add_tooltip(self.autostop_label, "Change the maximum recording length")
        self.disk_var = tk.StringVar(value="")
        self.disk_label = ttk.Label(self._live, textvariable=self.disk_var, style=LBL_DIM)
        self.disk_label.pack(anchor="w", padx=S_3)
        # Stop is packed first (side=bottom) so a long roster can never squeeze it out.
        self.stop_btn = ttk.Button(
            self._live, text="Stop recording", style=BTN_DANGER, command=self.stop
        )
        self.stop_btn.pack(side="bottom", anchor="e", **pad)
        self._people = ttk.Frame(self._live)
        self._people.pack(fill="both", expand=True, **pad)

        self._show(self._consent)

    # ---------- plumbing ----------

    def _show(self, frame: ttk.Frame) -> None:
        for f in (self._consent, self._picker, self._live):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    def _ui(self, fn, *args) -> None:
        """Run fn(*args) on the Tk thread (safe from workers; a dead window is a no-op)."""
        try:
            self.after(0, fn, *args)
        except (tk.TclError, RuntimeError):
            pass

    def destroy(self) -> None:
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None
        rec = self.recorder
        if self.state in ("starting", "recording") and rec is not None and rec.running:
            # window destroyed under a live recorder: let it stop itself, leave .pcm for recovery
            try:
                rec.request_stop()
            except Exception as e:
                config.log_exception("discord_record_dialog.request_stop", e)
        if getattr(self.app, "discord_recorder_dialog", None) is self:
            self.app.discord_recorder_dialog = None
        super().destroy()

    def _on_close(self) -> None:
        if self.state == "stopping":
            return  # finalize is converting; the window closes itself when it is done
        if self.state in ("starting", "recording"):
            if messagebox.askyesno(
                "Recording",
                "A Discord recording is running. Stop it and close this window?",
                parent=self,
            ):
                self.stop(reason="user" if self.state == "recording" else "cancel")
            return
        self.destroy()

    def _fail_if_still_starting(self) -> None:
        if self.state == "starting":
            self._fail(self._last_error_msg or "The recorder stopped before joining the channel.")

    def _open_limit_settings(self) -> None:
        self.app.open_settings(focus="discord_max_length")

    # ---------- starting ----------

    def _start_auto(self) -> None:
        self._launch(None)

    def _launch(self, channel_id: str | None) -> None:
        self._gen += 1
        gen = self._gen
        self._discard_previous_dir()
        self.out_dir = discord_recorder.new_recording_dir(self.session_id)
        notice = config.load_config().get("discord_notice", "")
        self.state = "starting"
        self._last_error_msg = ""
        self._exit_ticks = 0
        self.status_var.set("Connecting to Discord…")
        self._show(self._live)
        self.stop_btn.state(["disabled"])
        self.recorder = self._factory(
            self.out_dir,
            notice=notice,
            channel_id=channel_id,
            on_event=lambda ev, g=gen: self._ui(self._handle, ev, g),
        )
        try:
            self.recorder.start()
        except (RecorderError, RecorderUnavailable) as e:
            self._fail(str(e))
            return
        self._tick_id = self.after(1000, self._tick)

    def _discard_previous_dir(self) -> None:
        d = self.out_dir
        if not d or not os.path.isdir(d):
            return
        try:
            if not any(n.endswith(".pcm") for n in os.listdir(d)):
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass

    def _fail(self, message: str) -> None:
        self.state = "error"
        self._error_msg = message
        if self.recorder is not None:
            try:
                self.recorder.request_stop()
            except Exception as e:
                config.log_exception("discord_record_dialog.reap", e)
        self.status_var.set(message)
        self._show(self._live)
        self.stop_btn.state(["disabled"])

    # ---------- picker ----------

    def _enter_picker(self) -> None:
        old = self.recorder
        self.state = "picker"
        self.status_var.set("Looking up your servers…")
        self._show(self._picker)
        self.picker_start_btn.state(["disabled"])

        def work():
            if old is not None:
                try:
                    old.stop()
                except Exception as e:  # reaping a dead recorder must not block the picker
                    config.log_exception("discord_record_dialog.reap", e)
            try:
                inv = discord_recorder.list_inventory()
            except Exception as e:
                self._ui(self._inventory_failed, str(e) or type(e).__name__)
                return
            self._ui(self._fill_picker, inv)

        self._spawn(work)

    def _inventory_failed(self, message: str) -> None:
        if self.state == "picker":
            self.status_var.set(message)

    def _fill_picker(self, inv: dict) -> None:
        if self.state != "picker":
            return
        self._inventory = inv
        guilds = inv.get("guilds") or []
        self.guild_combo["values"] = [g["name"] for g in guilds]
        cfg = config.load_config()
        gi = next((i for i, g in enumerate(guilds) if g["id"] == cfg.get("discord_last_guild")), 0)
        if guilds:
            self.guild_combo.current(gi)
        self._on_guild_selected(preselect=cfg.get("discord_last_channel"))
        self.status_var.set("" if guilds else "The bot isn't in any server yet.")
        self.picker_start_btn.state(["!disabled"] if guilds else ["disabled"])

    def _channels(self) -> list[dict]:
        guilds = self._inventory.get("guilds") or []
        i = self.guild_combo.current()
        return (guilds[i].get("voice_channels") or []) if 0 <= i < len(guilds) else []

    def _on_guild_selected(self, preselect: str | None = None) -> None:
        chans = self._channels()
        self.channel_combo["values"] = [c["name"] for c in chans]
        self.channel_combo.set("")
        if chans:
            ci = next((i for i, c in enumerate(chans) if c["id"] == preselect), 0)
            self.channel_combo.current(ci)

    def _start_picked(self) -> None:
        guilds = self._inventory.get("guilds") or []
        gi, chans, ci = self.guild_combo.current(), self._channels(), self.channel_combo.current()
        if not (0 <= gi < len(guilds)) or not (0 <= ci < len(chans)):
            return
        cfg = config.load_config()
        cfg["discord_last_guild"] = guilds[gi]["id"]
        cfg["discord_last_channel"] = chans[ci]["id"]
        config.save_config(cfg)
        self._launch(chans[ci]["id"])

    # ---------- events (always on the Tk thread) ----------

    def _handle(self, ev: dict, gen: int) -> None:
        if gen != self._gen or self.state in ("stopping", "done", "error", "picker", "consent"):
            return
        kind = ev.get("event")
        if kind == "joined":
            self.state = "recording"
            self._started_at = self._now()
            self._exit_ticks = 0
            self._last_limit = self._limit()
            self.stop_btn.state(["!disabled"])
            where = " / ".join(x for x in (ev.get("guild_name"), ev.get("channel_name")) if x)
            self.status_var.set(f"Recording in {where}" if where else "Recording")
            self._tick()
        elif kind == "user":
            self._set_person(str(ev.get("id")), ev.get("name"))
        elif kind == "speaking":
            uid = str(ev.get("id"))
            self._set_person(uid, None)
            self._last_speak[uid] = self._now()
            self._refresh_dots()
        elif kind == "telemetry":
            for uid, info in (ev.get("users") or {}).items():
                self._set_person(str(uid), None)
                self._rows[str(uid)]["mins"].set(f"{int(info.get('seconds', 0)) // 60} min")
        elif kind == "reconnecting":
            self.status_var.set("Reconnecting to Discord…")
        elif kind == "rejoined":
            self.status_var.set("Recording")
        elif kind == "error":
            if ev.get("code") == "owner_not_in_voice" and self.state == "starting":
                self._enter_picker()
            else:
                self._error_msg = str(ev.get("message") or ev.get("code") or "Recorder error.")
                self._last_error_msg = self._error_msg
                self.stop(reason="error")

    def _set_person(self, uid: str, name: str | None) -> None:
        row = self._rows.get(uid)
        if row is None:
            frame = ttk.Frame(self._people)
            frame.pack(fill="x")
            dot = ttk.Label(frame, text="●", style=LBL_DIM)
            dot.pack(side="left")
            name_var, mins = tk.StringVar(value=name or uid), tk.StringVar(value="0 min")
            ttk.Label(frame, textvariable=name_var).pack(side="left", padx=S_2)
            ttk.Label(frame, textvariable=mins, style=LBL_DIM).pack(side="right")
            row = self._rows[uid] = {"dot": dot, "name": name_var, "mins": mins, "lit": False}
        elif name:
            row["name"].set(name)

    def _refresh_dots(self) -> None:
        t = self._now()
        for uid, row in self._rows.items():
            lit = (t - self._last_speak.get(uid, -1e9)) < DOT_HOLD_S
            row["lit"] = lit
            row["dot"].configure(style=LBL_STATUS_WARN if lit else LBL_DIM)

    # test/inspection helpers
    def person_ids(self) -> list[str]:
        return list(self._rows)

    def person_name(self, uid: str) -> str:
        return self._rows[uid]["name"].get()

    def person_lit(self, uid: str) -> bool:
        return self._rows[uid]["lit"]

    def person_minutes(self, uid: str) -> str:
        return self._rows[uid]["mins"].get()

    # ---------- tick ----------

    @staticmethod
    def _limit() -> int:
        try:
            return int(config.load_config().get("discord_max_minutes", 360) or 360)
        except (TypeError, ValueError):
            return 360

    def _tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None
        if self.state == "starting":
            rec = self.recorder
            if rec is not None and not rec.running:
                # Its last events (e.g. owner_not_in_voice) may still be in the reader thread
                # or on the after(0) queue: fail only on a later tick, once the reader is done.
                self._exit_ticks += 1
                done = getattr(rec, "readers_done", True)
                if (done and self._exit_ticks >= 2) or self._exit_ticks >= MAX_EXIT_DEFERRALS:
                    # final re-check after idle so an already-queued _handle runs first
                    self.after_idle(self._fail_if_still_starting)
                    return
                self._tick_id = self.after(300, self._tick)
            else:
                self._tick_id = self.after(1000, self._tick)
            return
        if self.state != "recording" or self._started_at is None:
            return
        rec = self.recorder
        if rec is not None and not rec.running:
            # Same deferral as starting: its final `error` event may still be in flight.
            self._exit_ticks += 1
            done = getattr(rec, "readers_done", True)
            if (done and self._exit_ticks >= 2) or self._exit_ticks >= MAX_EXIT_DEFERRALS:
                self.after_idle(self._stop_if_still_recording)
                return
            self._tick_id = self.after(300, self._tick)
            return
        elapsed = self._now() - self._started_at
        self.elapsed_var.set(fmt_hms(elapsed))
        self._refresh_dots()
        self._update_disk()
        limit = self._limit()
        text, style = autostop_text(elapsed, limit)
        self.autostop_text_value, self.autostop_style = text, style
        self.autostop_label.configure(text=text, style=_STYLES[style])
        action = self._check_limit(elapsed, limit)
        self._last_limit = limit
        if action == "auto":
            self.stop(reason="max_length")
        elif action == "ask":
            if messagebox.askyesno(
                "Maximum length already reached",
                f"The new maximum ({fmt_hm(limit)}) is shorter than this recording "
                f"({fmt_hms(elapsed)}). Stop recording now?",
                parent=self,
            ):
                self.stop(reason="user")
            else:
                self._suspended_for_limit = limit
        if self.state == "recording":
            self._tick_id = self.after(1000, self._tick)

    def _stop_if_still_recording(self) -> None:
        if self.state == "recording":
            self._error_msg = self._last_error_msg or "The recorder stopped unexpectedly."
            self.stop(reason="error")

    def _check_limit(self, elapsed: float, limit: int) -> str | None:
        if elapsed < limit * 60:
            self._suspended_for_limit = None
            return None
        if self._suspended_for_limit == limit:
            return None
        if self._last_limit is not None and limit != self._last_limit:
            return "ask"  # the limit was lowered below the elapsed time
        return "auto"  # time simply ran out

    def _update_disk(self) -> None:
        try:
            free = shutil.disk_usage(self.out_dir).free
        except OSError:
            self.disk_var.set("")
            return
        gb = free / 1024**3
        if free < LOW_DISK_BYTES:
            self.disk_var.set(f"⚠ Low disk space: {gb:.1f} GB free")
            self.disk_label.configure(style=LBL_STATUS_WARN)
        else:
            self.disk_var.set(f"{gb:.1f} GB free")
            self.disk_label.configure(style=LBL_DIM)

    # ---------- stopping ----------

    def stop(self, reason: str = "user") -> None:
        if self._stopping:
            return
        self._stopping = True
        self.state = "stopping"
        self.stop_btn.state(["disabled"])
        if reason == "max_length":
            self.status_var.set(AUTO_STOPPED_TEXT)
        else:
            self.status_var.set("Stopping and converting the recording…")
        rec, out_dir = self.recorder, self.out_dir

        def work():
            try:
                if rec is not None:
                    rec.stop()
                wavs, failures = discord_recorder.finalize(out_dir)
            except Exception as e:
                config.log_exception("discord_record_dialog.finalize", e)
                wavs, failures = [], {"": str(e) or type(e).__name__}
            self._ui(self._finished, reason, list(wavs), dict(failures))

        self._spawn(work)

    def _finished(self, reason: str, wavs: list[str], failures: dict) -> None:
        if wavs:
            self._attach(wavs)
        if reason == "error":
            self._end_with_message(self._error_msg or "The recording stopped because of an error.")
            return
        if reason == "cancel":
            self.destroy()
            return
        if reason == "quit":
            # app is quitting: tracks are attached (or the raw audio is kept); no hand-off
            self.state = "done"
            self.destroy()
            return
        if failures:
            self._end_with_message(
                f"{len(failures)} track(s) could not be converted. The raw audio is kept in:"
            )
            return
        if not wavs:
            self._end_with_message("No audio was captured.")
            return
        params: dict = {"mode": "tracks"}
        if reason == "max_length":
            params["notice"] = (
                "Recording stopped automatically at the maximum recording length "
                f"({fmt_hm(self._limit())}). Tracks attached."
            )
        self.destroy()
        self.app.open_session_stage(self.session_id, "transcribe", run_params=params)

    def _end_with_message(self, message: str) -> None:
        self.state = "error"
        self.stop_btn.state(["disabled"])
        self._show(self._live)
        self.status_var.set(f"{message}\n{self.out_dir}")

    def _attach(self, wavs: list[str]) -> None:
        m = self._session_view
        try:
            alive = m is not None and bool(m.winfo_exists())
        except tk.TclError:
            alive = False
        if alive and hasattr(m, "attach_audio"):
            m.attach_audio(wavs)
            return
        attach_wavs_to_db(self.session_id, wavs)
