"""Discord recording safety: quit-while-recording prompt, interrupted-recording recovery."""

from __future__ import annotations

import json
import types

import pytest

from app import config
from app.core import discord_recorder
from app.data import db
from app.ui import app_window
from app.ui.app_window import AppWindow

pytestmark = pytest.mark.gui

QUIT_PROMPT = "A Discord recording is running. Stop it and quit?"


class FakeDialog:
    def __init__(self, state, *, finish_on_stop=True):
        self.state = state
        self.finish_on_stop = finish_on_stop
        self.stops: list[str] = []
        self.exists = True

    def stop(self, reason="user"):
        self.stops.append(reason)
        if self.finish_on_stop:
            self.state = "done"

    def winfo_exists(self):
        return self.exists


class FakeApp:
    """Borrows AppWindow's methods without building a real window."""

    _on_close = AppWindow._on_close
    _await_recorder_then_close = AppWindow._await_recorder_then_close
    _maybe_recover_recordings = AppWindow._maybe_recover_recordings

    def __init__(self, dlg=None):
        self.discord_recorder_dialog = dlg
        self.closed = 0
        self.afters: list[tuple] = []

    def _close_now(self):
        self.closed += 1

    def after(self, ms, fn, *args):
        self.afters.append((ms, fn, args))

    def run_afters(self):
        while self.afters:
            _ms, fn, args = self.afters.pop(0)
            fn(*args)


@pytest.fixture
def asks(monkeypatch):
    calls: list[tuple] = []
    answer = {"v": True}

    def fake(title, message, **kw):
        calls.append((title, message))
        return answer["v"]

    monkeypatch.setattr("tkinter.messagebox.askyesno", fake)
    return types.SimpleNamespace(calls=calls, answer=answer)


def test_quit_while_recording_no_keeps_app_open(asks):
    asks.answer["v"] = False
    dlg = FakeDialog("recording")
    app = FakeApp(dlg)
    app._on_close()
    assert asks.calls[0][1] == QUIT_PROMPT
    assert app.closed == 0
    assert dlg.stops == []


def test_quit_while_recording_yes_stops_then_closes(asks):
    dlg = FakeDialog("recording")
    app = FakeApp(dlg)
    app._on_close()
    assert asks.calls[0][1] == QUIT_PROMPT
    assert dlg.stops == ["quit"]
    app.run_afters()
    assert app.closed == 1


def test_quit_waits_for_slow_finalize_then_closes(asks):
    dlg = FakeDialog("recording", finish_on_stop=False)
    app = FakeApp(dlg)
    app._on_close()
    assert dlg.stops == ["quit"]
    assert app.closed == 0
    assert app.afters and app.afters[0][0] == 200
    ms, fn, args = app.afters.pop(0)
    fn(*args)  # still stopping: re-arms, does not close
    assert app.closed == 0
    dlg.state = "done"
    app.run_afters()
    assert app.closed == 1


def test_quit_gives_up_after_120_seconds(asks):
    dlg = FakeDialog("stopping", finish_on_stop=False)
    app = FakeApp(dlg)
    app._on_close()
    n = 0
    while app.afters:
        _ms, fn, args = app.afters.pop(0)
        fn(*args)
        n += 1
        assert n < 1000
    assert app.closed == 1
    assert n * 0.2 >= 120 - 0.2


def test_quit_closes_if_dialog_vanishes(asks):
    dlg = FakeDialog("stopping", finish_on_stop=False)
    app = FakeApp(dlg)
    app._on_close()
    dlg.exists = False
    app.run_afters()
    assert app.closed == 1


@pytest.mark.parametrize("state", ["done", "error", "consent", "picker"])
def test_quit_without_active_recording_does_not_prompt(asks, state):
    app = FakeApp(FakeDialog(state))
    app._on_close()
    assert asks.calls == []
    assert app.closed == 1


def test_quit_without_dialog_does_not_prompt(asks):
    app = FakeApp(None)
    app._on_close()
    assert asks.calls == []
    assert app.closed == 1


def test_startup_prompts_include_recovery_step():
    import inspect

    assert "_maybe_recover_recordings" in inspect.getsource(AppWindow._run_startup_prompts)


# ---------- recovery ----------


@pytest.fixture
def rec_root(tmp_path):
    db.init_db()
    root = tmp_path / "recs"
    root.mkdir()
    cfg = config.load_config()
    cfg["recordings_folder"] = str(root)
    config.save_config(cfg)
    return root


def _folder(root, sid, ts="20261001_200000"):
    d = root / f"session_{sid}_{ts}"
    d.mkdir()
    (d / "111.pcm").write_bytes(b"\0\0")
    return str(d)


def test_recovery_no_folders_no_prompt(rec_root, asks):
    FakeApp()._maybe_recover_recordings()
    assert asks.calls == []


def test_recovery_no_does_nothing(rec_root, asks, monkeypatch):
    _folder(rec_root, 1)
    asks.answer["v"] = False
    monkeypatch.setattr(
        discord_recorder, "finalize", lambda d: pytest.fail("finalize must not run")
    )
    FakeApp()._maybe_recover_recordings()
    assert asks.calls[0][1] == "Finish converting 1 interrupted recording(s)?"


def test_recovery_yes_attaches_and_reports_missing_session(rec_root, asks, monkeypatch):
    sid = db.create_session("Night 1")
    d1 = _folder(rec_root, sid)
    d2 = _folder(rec_root, 987654)
    finalized: list[str] = []

    def fake_finalize(d):
        finalized.append(d)
        return [d + "/Mike_111.wav"], {}

    monkeypatch.setattr(discord_recorder, "finalize", fake_finalize)
    infos: list[tuple] = []
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda t, m, **kw: infos.append((t, m)))
    FakeApp()._maybe_recover_recordings()
    assert asks.calls[0][1] == "Finish converting 2 interrupted recording(s)?"
    assert sorted(finalized) == sorted([d1, d2])
    files = json.loads(db.get_session(sid)["source_audio_files"])
    assert files == [d1 + "/Mike_111.wav"]
    assert len(infos) == 1
    assert d2 in infos[0][1] and d1 not in infos[0][1]


def test_recovery_survives_finalize_error(rec_root, asks, monkeypatch):
    _folder(rec_root, 1)

    def boom(d):
        raise RuntimeError("ffmpeg gone")

    monkeypatch.setattr(discord_recorder, "finalize", boom)
    FakeApp()._maybe_recover_recordings()  # must not raise


def test_module_exposes_quit_constant():
    assert app_window.QUIT_WAIT_POLLS * 0.2 == 120
