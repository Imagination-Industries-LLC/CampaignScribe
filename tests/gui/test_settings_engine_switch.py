"""Settings: Speech engine GPU/CPU switch row (installed mode only)."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

import pytest

pytestmark = pytest.mark.gui


class _Master(tk.Tk):
    closed = 0

    def _on_close(self):
        _Master.closed += 1


@pytest.fixture
def root():
    try:
        r = _Master()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    _Master.closed = 0
    try:
        yield r
    finally:
        r.destroy()


def _installed(monkeypatch, tmp_path, profile="gpu"):
    from app.ui import settings_dialog as sd

    monkeypatch.setattr(sd.paths, "mode", lambda: "installed")
    monkeypatch.setattr(sd.paths, "app_home", lambda: tmp_path)
    state = {"profile": profile} if profile else None
    monkeypatch.setattr(sd.bootstrap_core, "read_state", lambda: state)
    return sd


def test_hidden_without_state(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, profile=None)
    dlg = sd.SettingsDialog(root)
    try:
        assert not hasattr(dlg, "engine_btn")
    finally:
        dlg.destroy()


def test_hidden_in_dev_mode(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path)
    monkeypatch.setattr(sd.paths, "mode", lambda: "dev")
    dlg = sd.SettingsDialog(root)
    try:
        assert not hasattr(dlg, "engine_btn")
    finally:
        dlg.destroy()


def test_shows_gpu_and_switch_to_cpu(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, "gpu")
    dlg = sd.SettingsDialog(root)
    try:
        assert dlg.engine_label.cget("text") == "GPU (CUDA)"
        assert dlg.engine_btn.cget("text") == "Switch to CPU…"
    finally:
        dlg.destroy()


def test_shows_cpu_and_switch_to_gpu(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, "cpu")
    dlg = sd.SettingsDialog(root)
    try:
        assert dlg.engine_label.cget("text") == "CPU"
        assert dlg.engine_btn.cget("text") == "Switch to GPU…"
    finally:
        dlg.destroy()


def test_confirm_launches_and_closes(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, "gpu")
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    dlg = sd.SettingsDialog(root)
    dlg.engine_btn.invoke()
    assert "download the other speech engine (about " in asked[0][1]
    assert asked[0][1].endswith(" GB). Continue?")
    ((cmd, kw),) = calls
    assert cmd == [
        str(tmp_path / "python" / "pythonw.exe"),
        str(tmp_path / "bootstrap" / "launcher.py"),
        "--switch",
        "cpu",
    ]
    assert kw["env"]["CAMPAIGNSCRIBE_HOME"] == str(tmp_path)
    if sys.platform == "win32":
        assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert _Master.closed == 1


def test_decline_does_nothing(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, "cpu")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a))
    dlg = sd.SettingsDialog(root)
    try:
        dlg.engine_btn.invoke()
        assert not calls
        assert _Master.closed == 0
        assert dlg.winfo_exists()
    finally:
        dlg.destroy()


def test_popen_failure_shows_error_and_stays(root, monkeypatch, tmp_path):
    sd = _installed(monkeypatch, tmp_path, "gpu")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: errors.append(a))

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(subprocess, "Popen", boom)
    dlg = sd.SettingsDialog(root)
    try:
        dlg.engine_btn.invoke()
        assert errors
        assert _Master.closed == 0
        assert dlg.winfo_exists()
    finally:
        dlg.destroy()
