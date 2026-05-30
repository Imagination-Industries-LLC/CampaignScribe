"""Tests for app.ui.common helpers: open_url + add_privacy_note."""

from __future__ import annotations

import tkinter as tk

import pytest

from app.ui import common


def test_open_url_calls_webbrowser(monkeypatch):
    opened = {}
    monkeypatch.setattr(
        common.webbrowser, "open", lambda url, new=0: opened.update(url=url, new=new)
    )
    common.open_url("https://example.com/x")
    assert opened["url"] == "https://example.com/x"
    assert opened["new"] == 2


def test_open_url_ignores_empty(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        common.webbrowser, "open", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    )
    common.open_url("")
    assert called["n"] == 0


@pytest.mark.gui
def test_add_privacy_note_grid_parent():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    try:
        frame = tk.Frame(root)
        tk.Label(frame, text="x").grid(row=0, column=0)  # make it grid-managed
        note = common.add_privacy_note(frame, "hello note")
        assert note.cget("text") == "hello note"
        assert note.winfo_manager() == "grid"
    finally:
        root.destroy()


@pytest.mark.gui
def test_add_privacy_note_pack_parent():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    try:
        frame = tk.Frame(root)
        tk.Label(frame, text="x").pack()  # make it pack-managed
        note = common.add_privacy_note(frame, "packed note")
        assert note.cget("text") == "packed note"
        assert note.winfo_manager() == "pack"
    finally:
        root.destroy()
