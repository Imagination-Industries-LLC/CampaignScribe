"""Every subprocess launch must pass creationflags=CREATE_NO_WINDOW so Windows
does not flash a console window. On non-Windows CREATE_NO_WINDOW is 0 (a no-op),
so these assertions hold on the whole CI matrix.
"""

from __future__ import annotations

import subprocess

from app.core.proc import CREATE_NO_WINDOW


def test_constant_matches_platform():
    assert CREATE_NO_WINDOW == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_detect_nvidia_smi_passes_creationflags(monkeypatch):
    import app.core.transcriber as transcriber

    captured: dict = {}

    monkeypatch.setattr("shutil.which", lambda name: "/fake/nvidia-smi")

    def fake_check_output(*args, **kwargs):
        captured.update(kwargs)
        return b"FakeGPU 4090\n"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    assert transcriber._detect_nvidia_gpu_via_smi() == "FakeGPU 4090"
    assert captured.get("creationflags") == CREATE_NO_WINDOW


def _fake_popen_recorder(captured: dict):
    def fake_popen(*args, **kwargs):
        captured.update(kwargs)

        class _Proc:
            pass

        return _Proc()

    return fake_popen


def test_open_path_native_passes_creationflags(monkeypatch):
    import app.ui.common as common

    captured: dict = {}
    monkeypatch.setattr(common.sys, "platform", "linux")  # force the xdg-open branch
    monkeypatch.setattr(common.subprocess, "Popen", _fake_popen_recorder(captured))

    common.open_path_native("/tmp/some/file.wav")
    assert captured.get("creationflags") == CREATE_NO_WINDOW


def test_reveal_in_folder_windows_explorer_passes_creationflags(monkeypatch):
    import app.ui.common as common

    captured: dict = {}
    monkeypatch.setattr(common.sys, "platform", "win32")  # force the explorer branch
    monkeypatch.setattr(common.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(common.subprocess, "Popen", _fake_popen_recorder(captured))

    common.reveal_in_folder(r"C:\sessions\file.txt")
    assert captured.get("creationflags") == CREATE_NO_WINDOW
