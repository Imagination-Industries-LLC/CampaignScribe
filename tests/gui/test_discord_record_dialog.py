"""Discord record dialog: consent, owner auto-join, picker, live panel, auto-stop, hand-off."""

from __future__ import annotations

import json
import tkinter as tk
import types

import pytest

from app import config
from app.core import discord_recorder
from app.data import db

pytestmark = pytest.mark.gui

NOTICE = "Test notice for the channel"
WAV = "C:/rec/Mike_123456789012345678.wav"


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


class FakeRecorder:
    def __init__(self, out_dir, *, notice, channel_id, on_event, cmd=None):
        self.out_dir = out_dir
        self.notice = notice
        self.channel_id = channel_id
        self.on_event = on_event
        self.started = False
        self.stops = 0
        self.running = False
        self.exit_code = None

    def start(self):
        self.started = True
        self.running = True

    def stop(self, timeout_s=15.0):
        self.stops += 1
        if self.running:
            self.running = False
            self.exit_code = 0
            self.on_event({"event": "stopped", "seconds": 1})
        return self.exit_code

    def emit(self, ev):
        self.on_event(ev)


class Harness:
    def __init__(self, root, monkeypatch, tmp_path):
        self.root = root
        self.clock = [1000.0]
        self.recorders: list[FakeRecorder] = []
        self.finalize_calls: list[str] = []
        self.finalize_result = ([WAV], {})
        self.asks: list[tuple] = []
        self.ask_answer = False
        self.opened_settings: list[dict] = []
        self.opened_stage: list[tuple] = []
        db.init_db()
        self.sid = db.create_session("Night 1")
        cfg = config.load_config()
        cfg["discord_notice"] = NOTICE
        config.save_config(cfg)
        self.app = types.SimpleNamespace(
            discord_recorder_dialog=None,
            open_settings=lambda **kw: self.opened_settings.append(kw),
            open_session_stage=lambda sid, stage, run_params=None: self.opened_stage.append(
                (sid, stage, run_params)
            ),
        )
        monkeypatch.setattr(discord_recorder, "get_token", lambda: "tok")
        monkeypatch.setattr(
            discord_recorder,
            "finalize",
            lambda out_dir: (self.finalize_calls.append(out_dir), self.finalize_result)[1],
        )
        monkeypatch.setattr(
            discord_recorder, "new_recording_dir", lambda sid: str(tmp_path / f"rec{sid}")
        )
        (tmp_path / f"rec{self.sid}").mkdir()
        monkeypatch.setattr(
            discord_recorder,
            "list_inventory",
            lambda timeout_s=20.0, token=None: {
                "guilds": [
                    {"id": "1", "name": "MDMT", "voice_channels": [{"id": "2", "name": "Table"}]},
                    {"id": "3", "name": "Other", "voice_channels": [{"id": "4", "name": "Lobby"}]},
                ],
                "owner": {"id": "9", "name": "Mike"},
                "owner_voice": None,
                "application_id": "5",
            },
        )

        def ask(title, message, **kw):
            self.asks.append((title, message))
            return self.ask_answer

        monkeypatch.setattr("tkinter.messagebox.askyesno", ask)

    def factory(self, *a, **kw):
        r = FakeRecorder(*a, **kw)
        self.recorders.append(r)
        return r

    def dialog(self, master=None):
        from app.ui.discord_record_dialog import DiscordRecordDialog

        return DiscordRecordDialog(
            master or self.root,
            self.app,
            self.sid,
            now=lambda: self.clock[0],
            recorder_factory=self.factory,
            spawn=lambda fn: fn(),
        )

    def pump(self):
        self.root.update()

    def set_limit(self, minutes):
        cfg = config.load_config()
        cfg["discord_max_minutes"] = minutes
        config.save_config(cfg)

    def recording(self, limit=None):
        if limit is not None:
            self.set_limit(limit)
        dlg = self.dialog()
        dlg.start_btn.invoke()
        self.recorders[-1].emit(
            {
                "event": "joined",
                "guild_id": "1",
                "guild_name": "MDMT",
                "channel_id": "2",
                "channel_name": "Table",
            }
        )
        self.pump()
        assert dlg.state == "recording"
        return dlg

    def advance(self, seconds):
        self.clock[0] += seconds


@pytest.fixture
def h(root, monkeypatch, tmp_path):
    return Harness(root, monkeypatch, tmp_path)


def test_consent_shows_notice_and_cancel_never_starts(h):
    dlg = h.dialog()
    assert dlg.state == "consent"
    text = dlg.consent_label.cget("text")
    assert "Everyone in the voice channel will be recorded." in text
    assert text.endswith("\n\n" + NOTICE)
    assert h.app.discord_recorder_dialog is dlg
    dlg.cancel_btn.invoke()
    assert not dlg.winfo_exists()
    assert h.recorders == []
    assert h.app.discord_recorder_dialog is None


def test_owner_auto_join(h):
    dlg = h.dialog()
    dlg.start_btn.invoke()
    rec = h.recorders[0]
    assert rec.channel_id is None
    assert rec.notice == NOTICE
    assert rec.started
    assert dlg.state == "starting"
    rec.emit(
        {
            "event": "joined",
            "guild_id": "1",
            "guild_name": "G",
            "channel_id": "2",
            "channel_name": "Table",
        }
    )
    h.pump()
    assert dlg.state == "recording"


def test_picker_fallback_and_remembered_choice(h):
    cfg = config.load_config()
    cfg["discord_last_guild"] = "3"
    cfg["discord_last_channel"] = "4"
    config.save_config(cfg)
    dlg = h.dialog()
    dlg.start_btn.invoke()
    h.recorders[0].emit({"event": "error", "code": "owner_not_in_voice", "message": "x"})
    h.pump()
    assert dlg.state == "picker"
    assert dlg.guild_combo.get() == "Other"
    assert dlg.channel_combo.get() == "Lobby"
    # pick the other guild/channel and start
    dlg.guild_combo.current(0)
    dlg._on_guild_selected()
    assert dlg.channel_combo.get() == "Table"
    dlg.picker_start_btn.invoke()
    assert h.recorders[1].channel_id == "2"
    cfg = config.load_config()
    assert cfg["discord_last_guild"] == "1"
    assert cfg["discord_last_channel"] == "2"
    assert dlg.state == "starting"
    # the first (dead) recorder's late events are ignored
    h.recorders[0].emit(
        {
            "event": "joined",
            "guild_id": "1",
            "guild_name": "G",
            "channel_id": "2",
            "channel_name": "T",
        }
    )
    h.pump()
    assert dlg.state == "starting"


def test_person_rows_and_dot(h):
    dlg = h.recording()
    rec = h.recorders[-1]
    rec.emit({"event": "user", "id": "11", "name": "Mike"})
    rec.emit({"event": "speaking", "id": "11"})
    h.pump()
    assert dlg.person_name("11") == "Mike"
    assert dlg.person_lit("11") is True
    # the name resolving later updates the same row
    rec.emit({"event": "user", "id": "11", "name": "Mike R"})
    h.pump()
    assert dlg.person_name("11") == "Mike R"
    assert len(dlg.person_ids()) == 1
    h.advance(2)
    dlg._tick()
    assert dlg.person_lit("11") is False


def test_telemetry_minutes(h):
    dlg = h.recording()
    h.recorders[-1].emit({"event": "user", "id": "11", "name": "Mike"})
    h.recorders[-1].emit(
        {
            "event": "telemetry",
            "elapsed_s": 130,
            "rss_mb": 1,
            "decode_errors": 0,
            "users": {"11": {"seconds": 125, "packets": 5}},
        }
    )
    h.pump()
    assert dlg.person_minutes("11") == "2 min"


def test_autostop_line_and_auto_stop(h):
    dlg = h.recording(limit=1)
    h.advance(30)
    dlg._tick()
    assert dlg.autostop_text_value == "\u23f1 Auto-stop in 0:30"
    assert dlg.autostop_style == "warn"
    h.advance(30)
    dlg._tick()
    h.pump()
    assert h.recorders[-1].stops == 1
    assert dlg.status_var.get() == "Stopped automatically at the maximum recording length."
    assert len(h.finalize_calls) == 1
    assert json.loads(db.get_session(h.sid)["source_audio_files"]) == [WAV]
    assert h.opened_stage == [(h.sid, "transcribe", {"mode": "tracks"})]
    assert not dlg.winfo_exists()


def test_limit_change_mid_recording(h):
    dlg = h.recording(limit=1)
    h.set_limit(120)
    dlg._tick()
    assert "Auto-stop at 2:00" in dlg.autostop_text_value


def test_limit_already_passed_no_then_rearm(h):
    dlg = h.recording(limit=360)
    h.advance(30 * 60)
    dlg._tick()
    h.set_limit(10)
    dlg._tick()
    assert [a[0] for a in h.asks] == ["Maximum length already reached"]
    assert h.asks[0][1] == (
        "The new maximum (0:10) is shorter than this recording (0:30:00). Stop recording now?"
    )
    assert dlg.state == "recording"
    assert dlg.autostop_style == "error"
    assert dlg.autostop_text_value.startswith("\u23f1 Past the maximum length")
    h.advance(5)
    dlg._tick()
    dlg._tick()
    assert len(h.asks) == 1
    assert dlg.state == "recording"
    h.set_limit(60)
    dlg._tick()
    assert dlg.autostop_style == "normal"
    assert dlg.state == "recording"
    h.advance(30 * 60)
    dlg._tick()
    h.pump()
    assert h.recorders[-1].stops == 1
    assert len(h.finalize_calls) == 1


def test_limit_already_passed_yes_stops(h):
    dlg = h.recording(limit=360)
    h.advance(30 * 60)
    dlg._tick()
    h.set_limit(10)
    h.ask_answer = True
    dlg._tick()
    h.pump()
    assert h.recorders[-1].stops == 1
    assert len(h.finalize_calls) == 1
    assert h.opened_stage == [(h.sid, "transcribe", {"mode": "tracks"})]


def test_autostop_label_opens_settings(h):
    dlg = h.recording()
    dlg._open_limit_settings()
    assert h.opened_settings == [{"focus": "discord_max_length"}]
    dlg.autostop_label.event_generate("<Button-1>")
    assert len(h.opened_settings) == 2


def test_double_stop_finalizes_once(h):
    dlg = h.recording(limit=1)
    dlg.stop()
    dlg.stop()
    dlg.stop_btn.invoke()
    h.pump()
    h.advance(120)
    dlg._tick()
    assert len(h.finalize_calls) == 1
    assert h.recorders[-1].stops == 1
    assert json.loads(db.get_session(h.sid)["source_audio_files"]) == [WAV]
    assert len(h.opened_stage) == 1


def test_recorder_error_finalizes_without_handoff(h):
    dlg = h.recording()
    rec = h.recorders[-1]
    rec.emit({"event": "error", "code": "voice_lost", "message": "Lost the voice connection."})
    rec.emit({"event": "stopped", "seconds": 5})
    h.pump()
    assert dlg.state == "error"
    assert "Lost the voice connection." in dlg.status_var.get()
    assert len(h.finalize_calls) == 1
    assert json.loads(db.get_session(h.sid)["source_audio_files"]) == [WAV]
    assert h.opened_stage == []
    assert dlg.winfo_exists()


def test_recorder_dying_silently_is_an_error(h):
    dlg = h.recording()
    h.recorders[-1].running = False
    dlg._tick()
    h.pump()
    assert dlg.state == "error"
    assert h.opened_stage == []


def test_attaches_via_session_view_when_master_has_it(h, root):
    from app.ui.session_view import SessionView

    view = SessionView(root, h.app, h.sid)
    dlg = h.dialog(master=view)
    dlg.start_btn.invoke()
    h.recorders[0].emit(
        {
            "event": "joined",
            "guild_id": "1",
            "guild_name": "G",
            "channel_id": "2",
            "channel_name": "T",
        }
    )
    h.pump()
    dlg.stop()
    h.pump()
    assert list(view.audio_box.get(0, "end")) == [WAV]
    assert json.loads(db.get_session(h.sid)["source_audio_files"]) == [WAV]
    view.destroy()


def _view(h, root):
    from app.ui.session_view import SessionView

    return SessionView(root, h.app, h.sid)


def test_button_without_token_offers_settings(h, root, monkeypatch):
    monkeypatch.setattr(discord_recorder, "get_token", lambda: "")
    h.ask_answer = True
    view = _view(h, root)
    view.record_btn.invoke()
    assert "Set up the Discord bot in Settings (\u2699) first." in h.asks[0][1]
    assert h.opened_settings == [{}]
    assert h.app.discord_recorder_dialog is None
    view.destroy()


def test_button_with_token_opens_single_dialog(h, root):
    view = _view(h, root)
    view.record_btn.invoke()
    dlg = h.app.discord_recorder_dialog
    assert dlg is not None and dlg.winfo_exists()
    view.record_btn.invoke()
    assert h.app.discord_recorder_dialog is dlg
    dlg.destroy()
    assert h.app.discord_recorder_dialog is None
    view.destroy()


def test_transcribe_handoff_sets_tracks_mode(root, tmp_path):
    from app.ui.transcribe_tab import TranscribeTab

    db.init_db()
    files = []
    for n in ("Mike_123456789012345678.wav", "Jo_223456789012345678.wav"):
        f = tmp_path / n
        f.write_bytes(b"RIFF")
        files.append(str(f))
    sid = db.create_session("Night", source_audio_files=files)
    tab = TranscribeTab(root, types.SimpleNamespace(notebook=None))
    tab.load_for_session(db.get_session(sid), run_params={"mode": "tracks"})
    assert tab.mode_var.get() == "tracks"
    assert [tab.track_meta[f]["speaker"] for f in files] == ["Mike", "Jo"]
    tab.load_for_session(db.get_session(sid), run_params=None)
    assert tab.mode_var.get() == "tracks"  # an explicit mode choice is not reset
