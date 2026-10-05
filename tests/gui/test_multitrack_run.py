"""Transcribe tab: the 'One file per speaker' run path, run synchronously with fakes."""

from __future__ import annotations

import json
import tkinter as tk
import types
import wave
from pathlib import Path

import pytest

from app import config
from app.data import db

pytestmark = pytest.mark.gui


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


class _SyncThread:
    def __init__(self, target=None, daemon=None, **_k):
        self._target = target

    def start(self):
        self._target()


def _write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


class _Env:
    def __init__(self, tab, tmp_path, sid):
        self.tab = tab
        self.tmp = tmp_path
        self.sid = sid
        self.out = tmp_path / "out"
        self.durations: dict[str, float] = {}
        self.convert_fail: set[str] = set()
        self.transcribe_calls: list[str] = []
        self.file_calls: list[str] = []
        self.cancel_on: str | None = None

    def run(self, mode: str = "tracks", names=("Mike", "Sarah")):
        tab = self.tab
        paths = [str(self.tmp / f"{n.lower()}.flac") for n in names]
        tab._set_audio_files(paths)
        if mode == "tracks":
            tab.mode_var.set("tracks")
            tab._apply_mode()
            for p, n in zip(paths, names, strict=True):
                tab._set_track(p, speaker=n)
        tab.out_var.set(str(self.out))
        tab._start()
        return paths


@pytest.fixture
def env(root, tmp_path, monkeypatch):
    from app.core import audio, llm, speaker_id, transcriber
    from app.ui import transcribe_tab as tt

    db.init_db()
    sid = db.create_session("S")

    cfg = config.load_config()
    cfg["voice_match_enabled"] = False
    config.save_config(cfg)

    tab = tt.TranscribeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    sp = tmp_path / "speakers.json"
    sp.write_text(json.dumps({"known_non_players": []}), encoding="utf-8")
    tab.speakers_path = str(sp)
    tab._session_index = [None, sid]
    tab.session_combo["values"] = ["(none)", f"#{sid}"]
    tab.session_combo.current(1)

    e = _Env(tab, tmp_path, sid)
    monkeypatch.setattr(tt.threading, "Thread", _SyncThread)
    monkeypatch.setattr(tab, "after", lambda ms, fn=None, *a: fn(*a) if fn else None)

    class FakePipeline:
        def __init__(self, **_k):
            self._last_speaker_embeddings = {}

        def transcribe_track(self, wav, diarize=False, progress=None, **kw):
            name = Path(wav).stem
            e.transcribe_calls.append(name)
            if e.cancel_on == name:
                tab._cancel.set()
            start = 0.0 if name.startswith("mike") else 1.0
            return [{"start": start, "end": start + 1.0, "text": f"hi from {name}"}]

        def transcribe_file(self, wav, progress=None, **kw):
            e.file_calls.append(wav)
            return [{"start": 0.0, "end": 1.0, "text": "mixed", "speaker": "SPEAKER_00"}]

        def close(self):
            pass

    monkeypatch.setattr(transcriber, "TranscriptionPipeline", FakePipeline)

    def fake_convert(src, *a, **k):
        stem = Path(src).stem
        if stem in e.convert_fail:
            raise RuntimeError("bad file")
        out = tmp_path / f"{stem}.wav"
        _write_wav(out, e.durations.get(stem, 1.0))
        return str(out)

    monkeypatch.setattr(audio, "convert_to_wav", fake_convert)

    def no_ai(*a, **k):
        raise AssertionError("identify_speakers must not run in tracks mode")

    monkeypatch.setattr(speaker_id, "identify_speakers", no_ai)
    monkeypatch.setattr(
        speaker_id,
        "refine_speakers",
        lambda *a, **k: {"improvements": [], "new_speakers": [], "suggested_ignores": []},
    )
    monkeypatch.setattr(llm, "get_provider", lambda: object())
    monkeypatch.setattr(llm, "provider_ready", lambda: True)
    monkeypatch.setattr(tt.messagebox, "showerror", lambda *a, **k: pytest.fail(str(a)))
    monkeypatch.setattr(tt.messagebox, "showinfo", lambda *a, **k: None)
    return e


def _glob(env, pat):
    return sorted(env.out.glob(pat))


def _row_state(tab, path):
    return tab.tree.set(tab.row_items[path], "state")


def test_tracks_run_writes_outputs_and_names_speakers(env):
    paths = env.run()
    assert len(_glob(env, "transcript_*_tracks.json")) == 1
    assert len(_glob(env, "speaker_mapping_*_tracks.json")) == 1
    assert len(_glob(env, "speakers_improvements_*.json")) == 1
    txts = _glob(env, "transcript_*_tracks.txt")
    assert len(txts) == 1
    mapping = json.loads(_glob(env, "speaker_mapping_*_tracks.json")[0].read_text("utf-8"))
    assert mapping == {"TRACK_01": "Mike", "TRACK_02": "Sarah"}
    lines = [ln for ln in txts[0].read_text("utf-8").splitlines() if ln.strip()]
    mike_i = next(i for i, ln in enumerate(lines) if "Mike:" in ln)
    sarah_i = next(i for i, ln in enumerate(lines) if "Sarah:" in ln)
    assert mike_i < sarah_i
    rows = {r["source_speaker_id"]: r["display_name"] for r in db.get_speakers_for_session(env.sid)}
    assert rows == {"TRACK_01": "Mike", "TRACK_02": "Sarah"}
    s = db.get_session(env.sid)
    assert s["status"] == "transcribed"
    assert s["num_speakers_detected"] == 2
    assert json.loads(s["source_audio_files"]) == paths
    assert not env.tab._busy


def test_failed_track_row_marked_and_rest_written(env):
    env.convert_fail = {"sarah"}
    paths = env.run()
    assert _row_state(env.tab, paths[1]).endswith("failed")
    assert _row_state(env.tab, paths[0]).endswith("complete")
    mapping = json.loads(_glob(env, "speaker_mapping_*_tracks.json")[0].read_text("utf-8"))
    assert mapping == {"TRACK_01": "Mike"}
    assert len(_glob(env, "transcript_*_tracks.txt")) == 1


def test_all_tracks_failed_writes_nothing(env):
    env.convert_fail = {"mike", "sarah"}
    env.run()
    assert _glob(env, "transcript_*") == []
    assert not env.tab._busy


def test_cancel_mid_run_writes_nothing(env):
    env.cancel_on = "sarah"
    paths = env.run()
    assert env.transcribe_calls == ["mike", "sarah"]
    assert _glob(env, "transcript_*_tracks.*") == []
    assert not env.tab._busy
    assert _row_state(env.tab, paths[1]).endswith("failed")


def test_duration_mismatch_warns_in_status(env):
    env.durations = {"mike": 1.0, "sarah": 10.0}
    env.run()
    assert "may not start together" in env.tab.status_var.get()
    assert len(_glob(env, "transcript_*_tracks.txt")) == 1


def test_mixed_mode_unchanged(env, monkeypatch):
    from app.core import llm, speaker_id

    monkeypatch.setattr(llm, "get_provider", lambda: types.SimpleNamespace(display_name="P"))
    monkeypatch.setattr(speaker_id, "identify_speakers", lambda *a, **k: {"SPEAKER_00": "X"})
    env.run(mode="mixed", names=("a", "b"))
    assert len(env.file_calls) == 2
    assert env.transcribe_calls == []
    assert len(_glob(env, "transcript_*_1.txt")) == 1
