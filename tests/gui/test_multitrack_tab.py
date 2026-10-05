"""Transcribe tab: 'One file per speaker' mode switch, track table, pre-flights."""

from __future__ import annotations

import threading
import tkinter as tk
import types

import pytest

from app import config
from app.core import multitrack

pytestmark = pytest.mark.gui

A = r"C:\r\a.wav"
B = r"C:\r\b.wav"


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


@pytest.fixture
def tab(root):
    from app.data import db
    from app.ui.transcribe_tab import TranscribeTab

    db.init_db()
    t = TranscribeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    return t


@pytest.fixture
def pick(monkeypatch):
    chosen: list[str] = []
    monkeypatch.setattr(
        "app.ui.transcribe_tab.filedialog.askopenfilenames", lambda **k: tuple(chosen)
    )

    def _set(paths):
        chosen[:] = paths

    return _set


@pytest.fixture
def errors(monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        "app.ui.transcribe_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    return shown


@pytest.fixture
def started(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(threading.Thread, "start", lambda self, *a, **k: calls.append(1))
    return calls


@pytest.fixture
def armed_tab(tab, tmp_path, errors, started):
    cfg = config.load_config()
    cfg["llm_provider"] = "anthropic"
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    sp = tmp_path / "speakers.json"
    sp.write_text("{}", encoding="utf-8")
    tab.speakers_path = str(sp)
    tab.out_var.set(str(tmp_path))
    return tab


def _rows(tab):
    return [tab.tracks_table.item(i, "values") for i in tab.tracks_table.get_children()]


def _tracks_mode(tab):
    tab.mode_var.set("tracks")
    tab._apply_mode()


def test_mode_switch_shows_track_table(tab):
    assert tab.mode_var.get() == "mixed"
    assert tab.tracks_table.winfo_manager() == ""
    _tracks_mode(tab)
    assert tab.tracks_table.winfo_manager() == "grid"
    assert tab.files_box.winfo_manager() == ""
    assert tab.spk_label.cget("text") == "# speakers per shared mic"
    assert tab.edit_track_btn.winfo_manager() == "pack"


def test_adding_files_prefills_names(tab, pick):
    _tracks_mode(tab)
    pick([r"C:\r\1-mike_1234.flac", r"C:\r\Sarah.m4a"])
    tab._add_files()
    assert _rows(tab) == [("1-mike_1234.flac", "mike", "☐"), ("Sarah.m4a", "Sarah", "☐")]


def test_set_track_updates_row_and_meta(tab, pick):
    _tracks_mode(tab)
    pick([A])
    tab._add_files()
    tab._set_track(A, speaker="Mike", shared_mic=True)
    assert tab.tracks_table.item(A, "values") == ("a.wav", "Mike", "☑")
    assert tab._tracks()[0] == multitrack.Track(A, "Mike", True)


def test_switching_back_to_mixed_keeps_files(tab, pick):
    _tracks_mode(tab)
    pick([A, B])
    tab._add_files()
    tab.mode_var.set("mixed")
    tab._apply_mode()
    assert list(tab.files_box.get(0, "end")) == [A, B]
    assert tab.spk_label.cget("text") == "# speakers:"
    assert tab.edit_track_btn.winfo_manager() == ""


def test_remove_selected_in_tracks_mode(tab, pick):
    _tracks_mode(tab)
    pick([A, B])
    tab._add_files()
    tab.tracks_table.selection_set(A)
    tab._remove_files()
    assert tab.audio_files == [B]
    assert list(tab.files_box.get(0, "end")) == [B]
    assert list(tab.track_meta) == [B]
    assert tab.tracks_table.get_children() == (B,)


def test_remove_selected_in_mixed_mode_updates_table(tab, pick):
    pick([A, B])
    tab._add_files()
    tab.files_box.selection_set(0)
    tab._remove_files()
    assert tab.audio_files == [B]
    assert list(tab.track_meta) == [B]
    assert tab.tracks_table.get_children() == (B,)


def test_clear_all_clears_meta_and_rows(tab, pick):
    _tracks_mode(tab)
    pick([A, B])
    tab._add_files()
    tab._clear_files()
    assert tab.audio_files == []
    assert tab.track_meta == {}
    assert tab.tracks_table.get_children() == ()
    assert tab.files_box.size() == 0


def test_set_audio_files_rebuilds_table(tab, monkeypatch):
    monkeypatch.setattr("app.ui.transcribe_tab.messagebox.showwarning", lambda *a, **k: None)
    tab._set_audio_files([r"C:\r\2-sam_99.flac", B])
    assert _rows(tab) == [("2-sam_99.flac", "sam", "☐"), ("b.wav", "b", "☐")]


def test_edit_dialog_ok_applies(tab, pick, monkeypatch):
    _tracks_mode(tab)
    pick([A])
    tab._add_files()
    monkeypatch.setattr("app.ui.transcribe_tab.TranscribeTab._player_names", lambda self: ["Mike"])
    dlg = tab._open_track_dialog(A)
    dlg.speaker_var.set("Mike")
    dlg.shared_var.set(True)
    dlg.ok_btn.invoke()
    assert tab.tracks_table.item(A, "values") == ("a.wav", "Mike", "☑")
    assert not dlg.winfo_exists()


def test_preflight_needs_two_tracks(armed_tab, errors, started):
    _tracks_mode(armed_tab)
    armed_tab.audio_files = [A]
    armed_tab.track_meta = {A: {"speaker": "A", "shared_mic": False}}
    armed_tab._start()
    assert errors == ["Add at least two files (one per speaker), or switch to Mixed recording."]
    assert started == []


def test_preflight_needs_names(armed_tab, errors, started):
    _tracks_mode(armed_tab)
    armed_tab.audio_files = [A, B]
    armed_tab.track_meta = {
        A: {"speaker": "A", "shared_mic": False},
        B: {"speaker": "  ", "shared_mic": False},
    }
    armed_tab._start()
    assert errors == ["Give every track a speaker name."]
    assert started == []


def test_valid_tracks_pass_preflights(armed_tab, errors, started):
    _tracks_mode(armed_tab)
    armed_tab.audio_files = [A, B]
    armed_tab.track_meta = {
        A: {"speaker": "A", "shared_mic": False},
        B: {"speaker": "B", "shared_mic": False},
    }
    armed_tab._start()
    assert errors == []
    assert started == [1]
