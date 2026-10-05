from pathlib import Path

import pytest

from bootstrap import core, launcher


class FakeRoot:
    def __init__(self):
        self.destroyed = False
        self.on_mainloop = None

    def mainloop(self):
        if self.on_mainloop:
            self.on_mainloop()

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def patched(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    popen = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: popen.append((a, k)))
    monkeypatch.setattr(core, "detect_nvidia", lambda: {"found": False, "name": "", "driver": ""})
    root = FakeRoot()
    monkeypatch.setattr(launcher, "_new_root", lambda: root)
    windows = []

    class FakeWindow:
        def __init__(self, r, **kw):
            self.kw = kw
            windows.append(self)

    monkeypatch.setattr(launcher, "SetupWindow", FakeWindow)
    return popen, windows, root


def _decide(monkeypatch, result):
    seen = []

    def fake(state, app_home, exists, switch):
        seen.append((app_home, exists, switch))
        return result

    monkeypatch.setattr(launcher, "decide", fake)
    return seen


def test_launch_branch_popens_app_and_returns_zero(patched, monkeypatch):
    popen, windows, _ = patched
    seen = _decide(monkeypatch, ("launch", "gpu"))
    home = Path(launcher.__file__).resolve().parent.parent
    assert launcher.main([]) == 0
    assert windows == []
    (argv,), kw = popen[0]
    assert argv[0].endswith("pythonw.exe") and Path(argv[1]).name == "main.py"
    assert kw["env"]["CAMPAIGNSCRIBE_HOME"] == str(home)
    assert seen[0][0] == home
    if launcher.sys.platform == "win32":
        assert kw["creationflags"] == launcher.subprocess.CREATE_NO_WINDOW


def test_switch_is_passed_to_decide_and_choice_shown(patched, monkeypatch):
    _, windows, _ = patched
    seen = _decide(monkeypatch, ("setup", "cpu"))
    launcher.main(["--switch", "cpu"])
    assert seen[0][2] == "cpu"
    assert windows[0].kw["profile_default"] == "cpu" and windows[0].kw["resetup"] is False


def test_bad_switch_value_exits(patched):
    with pytest.raises(SystemExit):
        launcher.main(["--switch", "tpu"])


def test_setup_branch_quit_returns_one(patched, monkeypatch):
    popen, windows, _ = patched
    _decide(monkeypatch, ("setup", None))
    assert launcher.main([]) == 1
    assert popen == [] and windows[0].kw["resetup"] is False


def test_resetup_branch_skips_choice_and_launches_on_done(patched, monkeypatch):
    popen, windows, root = patched
    _decide(monkeypatch, ("resetup", "gpu"))
    root.on_mainloop = lambda: windows[0].kw["on_done"]("gpu")
    assert launcher.main([]) == 0
    assert windows[0].kw["resetup"] is True
    assert windows[0].kw["profile_default"] == "gpu"
    assert root.destroyed and len(popen) == 1
