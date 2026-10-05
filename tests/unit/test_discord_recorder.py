"""Tests for app.core.discord_recorder (Tk-free; no Node needed)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import pytest

from app import config
from app.core import discord_recorder as dr
from app.core.audio import get_ffmpeg_path

FAKE = str(Path(__file__).with_name("fake_recorder.py"))


def _proc(tmp_path, events, mode, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", mode)
    out = tmp_path / "rec"
    out.mkdir(exist_ok=True)
    return dr.RecorderProcess(
        str(out),
        notice="n",
        channel_id=None,
        on_event=events.append,
        cmd=[sys.executable, FAKE, "--out", str(out)],
    )


def _wait(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _spoke(ev):
    return any(e["event"] == "speaking" for e in ev)


def test_events_in_order_and_stop(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "record_ok", monkeypatch)
    p.start()
    assert _wait(lambda: _spoke(ev))
    assert p.running
    assert p.stop() == 0
    assert not p.running
    assert [e["event"] for e in ev] == ["ready", "joined", "user", "speaking", "stopped"]
    assert p.stop() == 0  # idempotent


def test_request_stop_is_nonblocking_and_stop_still_clean(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "record_ok", monkeypatch)
    p.start()
    assert _wait(lambda: _spoke(ev))
    t0 = time.time()
    p.request_stop()
    p.request_stop()  # idempotent
    assert time.time() - t0 < 2.0
    assert _wait(lambda: not p.running)
    assert p.exit_code == 0
    assert p.stop() == 0
    p.request_stop()  # harmless after stop


def test_stdin_eof_stops(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "record_ok", monkeypatch)
    p.start()
    assert _wait(lambda: _spoke(ev))
    p._close_stdin()
    assert _wait(lambda: not p.running)
    assert p.exit_code == 0
    p.stop()


def test_owner_absent_exit_code(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "owner_absent", monkeypatch)
    p.start()
    assert _wait(lambda: not p.running)
    assert p.exit_code == 2
    assert p.stop() == 2
    assert any(e["event"] == "error" and e["code"] == "owner_not_in_voice" for e in ev)


def test_kill_on_timeout(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "hang", monkeypatch)
    p.start()
    assert _wait(lambda: bool(ev))
    t = time.time()
    code = p.stop(timeout_s=1)
    assert time.time() - t < 3
    assert code != 0
    assert not p.running


def test_garbage_lines_ignored(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "garbage", monkeypatch)
    p.start()
    assert _wait(lambda: not p.running)
    p.stop()
    assert [e["event"] for e in ev] == ["ready"]


def test_token_never_leaks(tmp_path, monkeypatch):
    secret = "SECRET123"
    config.save_discord_token(secret)
    assert dr.get_token() == secret
    ev = []
    p = _proc(tmp_path, ev, "leak_probe", monkeypatch)
    p.start()
    assert _wait(lambda: _spoke(ev))
    p.stop()
    out = tmp_path / "rec"
    # the child DID get the token through its environment ...
    assert (out / "env_seen.txt").read_text(encoding="utf-8") == secret
    (out / "env_seen.txt").unlink()
    # ... and it is nowhere else
    assert secret not in json.dumps(p.args)
    assert secret not in json.dumps(ev)
    assert all(secret not in line for line in p.stderr_lines)
    for f in out.iterdir():
        assert secret.encode() not in f.read_bytes()
    # errors raised to the caller do not carry it either
    _fake_node(monkeypatch, "list_error")
    with pytest.raises(dr.RecorderError) as ei:
        dr.list_inventory(token=secret)
    assert secret not in str(ei.value)
    assert secret not in ei.value.code
    bad = dr.RecorderProcess(
        str(out), notice="n", channel_id=None, on_event=ev.append, cmd=[str(tmp_path / "nope.exe")]
    )
    with pytest.raises(dr.RecorderError) as ei2:
        bad.start()
    assert secret not in str(ei2.value)


def test_flood_does_not_deadlock(tmp_path, monkeypatch):
    ev = []
    p = _proc(tmp_path, ev, "flood", monkeypatch)
    p.start()
    t = time.time()
    code = p.stop(timeout_s=20)
    assert time.time() - t < 15
    assert code == 0
    assert not p.running
    assert not p._reader.is_alive()
    assert not p._err_reader.is_alive()
    assert len(p.stderr_lines) == 200
    assert ev[-1]["event"] == "stopped"
    assert sum(1 for e in ev if e["event"] == "telemetry") == 5000


def test_start_launch_failure_is_recorder_error(tmp_path):
    p = dr.RecorderProcess(
        str(tmp_path),
        notice="n",
        channel_id=None,
        on_event=lambda e: None,
        cmd=[str(tmp_path / "nope.exe")],
    )
    with pytest.raises(dr.RecorderError) as ei:
        p.start()
    assert ei.value.code == "launch_failed"


def test_finalize_ffmpeg_gets_nostdin_and_devnull(tmp_path, monkeypatch):
    _write_pcm(tmp_path / "1.pcm", 1)
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        raise OSError("stop here")

    monkeypatch.setattr(dr.subprocess, "run", fake_run)
    dr.finalize(str(tmp_path), ffmpeg="ff")
    assert "-nostdin" in seen["cmd"]
    assert seen["kw"]["stdin"] == subprocess.DEVNULL


def test_sanitize_name_caps_length():
    assert dr.sanitize_name("a" * 300) == "a" * 80
    assert dr.sanitize_name(" " * 5 + "b" * 79 + " c") == "b" * 79


def test_no_token_raises_without_test_cmd(tmp_path):
    p = dr.RecorderProcess(str(tmp_path), notice="n", channel_id=None, on_event=lambda e: None)
    with pytest.raises(dr.RecorderError) as ei:
        p.start()
    assert ei.value.code == "no_token"


def _token(app_id: str) -> str:
    return base64.urlsafe_b64encode(app_id.encode()).decode().rstrip("=") + ".abc.def"


def test_application_id_and_invite():
    tok = _token("1234567890123")
    assert dr.application_id_from_token(tok) == "1234567890123"
    url = dr.invite_url(tok)
    assert "client_id=1234567890123" in url
    assert "scope=bot" in url
    assert "permissions=1051648" in url
    for bad in ("", "garbage", "!!!.x.y", _token("abc")):
        assert dr.application_id_from_token(bad) is None
        assert dr.invite_url(bad) is None


def _fake_node(monkeypatch, mode):
    monkeypatch.setenv("FAKE_MODE", mode)
    monkeypatch.setattr(dr, "_list_cmd", lambda: [sys.executable, FAKE, "--list"])
    config.save_discord_token("SECRET123")


def test_list_inventory_ok(monkeypatch):
    _fake_node(monkeypatch, "list_ok")
    inv = dr.list_inventory()
    assert inv["guilds"][0]["voice_channels"][0]["id"] == "20"


def test_list_inventory_error(monkeypatch):
    _fake_node(monkeypatch, "list_error")
    with pytest.raises(dr.RecorderError) as ei:
        dr.list_inventory()
    assert ei.value.code == "bad_token"


def test_list_inventory_uses_given_token(monkeypatch):
    _fake_node(monkeypatch, "list_ok")
    config.save_discord_token("")  # nothing stored; explicit token must be used
    assert dr.list_inventory(token="tmp.tok.en")["guilds"]
    with pytest.raises(dr.RecorderError) as ei:
        dr.list_inventory()
    assert ei.value.code == "no_token"


def test_list_inventory_timeout(monkeypatch):
    _fake_node(monkeypatch, "hang")
    with pytest.raises(dr.RecorderError) as ei:
        dr.list_inventory(timeout_s=1)
    assert ei.value.code == "timeout"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mike", "Mike"),
        ('a/b\\c:d*e?f"g<h>i|j', "a_b_c_d_e_f_g_h_i_j"),
        ("   ", "user"),
        ("", "user"),
        ("x\u0001y", "x_y"),
    ],
)
def test_sanitize_name(raw, expected):
    assert dr.sanitize_name(raw) == expected


def _ffmpeg_or_skip():
    ff = get_ffmpeg_path()
    if os.path.isabs(ff) and os.path.exists(ff):
        return ff
    found = shutil.which("ffmpeg")
    if not found:
        pytest.skip("ffmpeg not available")
    return found


def _write_pcm(path, seconds):
    Path(path).write_bytes(b"\x00\x00" * int(48000 * seconds))


def test_finalize_converts(tmp_path):
    ff = _ffmpeg_or_skip()
    _write_pcm(tmp_path / "1.pcm", 2)
    (tmp_path / "tracks.json").write_text(json.dumps({"1": "Mi/ke"}), encoding="utf-8")
    wavs, failures = dr.finalize(str(tmp_path), ffmpeg=ff)
    assert failures == {}
    assert [os.path.basename(w) for w in wavs] == ["Mi_ke_1.wav"]
    with wave.open(wavs[0]) as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getnframes() / 16000 == pytest.approx(2.0, abs=0.01)
    assert not (tmp_path / "1.pcm").exists()


def test_finalize_unnamed_falls_back_to_id(tmp_path):
    ff = _ffmpeg_or_skip()
    _write_pcm(tmp_path / "7.pcm", 1)
    wavs, failures = dr.finalize(str(tmp_path), ffmpeg=ff)
    assert failures == {}
    assert [os.path.basename(w) for w in wavs] == ["7_7.wav"]


def test_finalize_failure_keeps_pcm(tmp_path):
    _write_pcm(tmp_path / "1.pcm", 1)
    wavs, failures = dr.finalize(str(tmp_path), ffmpeg=str(tmp_path / "no_such_ffmpeg"))
    assert wavs == []
    assert str(tmp_path / "1.pcm") in failures
    assert (tmp_path / "1.pcm").exists()


def test_finalize_nonzero_exit_keeps_pcm(tmp_path):
    _write_pcm(tmp_path / "1.pcm", 1)
    wavs, failures = dr.finalize(str(tmp_path), ffmpeg=sys.executable)  # python rejects ffmpeg args
    assert wavs == []
    assert len(failures) == 1
    assert (tmp_path / "1.pcm").exists()


def test_unfinished_and_session_id(tmp_path):
    a = tmp_path / "session_1_x"
    b = tmp_path / "session_2_y"
    a.mkdir()
    b.mkdir()
    (a / "5.pcm").write_bytes(b"")
    (b / "tracks.json").write_text("{}")
    assert dr.unfinished_recordings(str(tmp_path)) == [str(a)]
    assert dr.unfinished_recordings(str(tmp_path / "missing")) == []
    assert dr.session_id_from_dir("/x/session_12_20261005_101010") == 12
    assert dr.session_id_from_dir("/x/session_12_20261005_101010/") == 12
    assert dr.session_id_from_dir("/x/other") is None
    assert dr.session_id_from_dir("/x/session_ab_1") is None


def test_recordings_root_precedence():
    assert dr.recordings_root({"recordings_folder": "R", "default_output_folder": "O"}) == "R"
    assert dr.recordings_root(
        {"recordings_folder": "", "default_output_folder": "O"}
    ) == os.path.join("O", "recordings")
    assert dr.recordings_root({}) == str(config.get_app_data_dir() / "recordings")


def test_new_recording_dir(tmp_path):
    cfg = {"recordings_folder": str(tmp_path / "r")}
    d = dr.new_recording_dir(12, datetime(2026, 10, 5, 10, 10, 10), cfg)
    assert d == os.path.join(str(tmp_path / "r"), "session_12_20261005_101010")
    assert os.path.isdir(d)


def test_node_exe_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert dr.node_exe() == str(tmp_path / "node" / "node.exe")
    assert dr.recorder_script() == str(tmp_path / "recorder" / "recorder.mjs")


def test_node_exe_dev_vendor(tmp_path, monkeypatch):
    (tmp_path / "vendor" / "node").mkdir(parents=True)
    exe = tmp_path / "vendor" / "node" / "node.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(dr, "_repo_root", lambda: tmp_path)
    assert dr.node_exe() == str(exe)
    assert dr.recorder_script() == str(tmp_path / "recorder" / "recorder.mjs")


def test_node_exe_path_fallback_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/node")
    assert dr.node_exe() == "/usr/bin/node"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    with pytest.raises(dr.RecorderUnavailable, match="python scripts/fetch_node_runtime.py"):
        dr.node_exe()
