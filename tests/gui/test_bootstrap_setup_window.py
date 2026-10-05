import tkinter as tk
from tkinter import messagebox

import pytest

from bootstrap import core, setup_window
from bootstrap.install import InstallResult
from bootstrap.setup_window import SetupWindow

pytestmark = pytest.mark.gui

GPU = {"found": True, "name": "RTX 4090", "driver": "555.1"}


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # pytest tmp paths exceed the 80-char env limit; the checks are exercised explicitly below
    monkeypatch.setattr(core, "path_ok", lambda p: True)
    monkeypatch.setattr(core, "disk_ok", lambda p, prof: (True, 50 * 1024**3))


class FakeInstaller:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.cancelled = False
        self.cleaned = False

    def __call__(self, profile, log_cb, progress_cb):
        if self.cancelled:
            return InstallResult(False, False, "Cancelled")
        self.calls.append(profile)
        for i in range(40):
            log_cb(f"line {i}")
        progress_cb(1, 4, "torch")
        res = self.results.pop(0)
        if res.ok:  # the real installer writes state only after a successful verify
            core.write_state(profile, "sha", "3.13.16")
        return res

    def cancel(self):
        self.cancelled = True

    def cleanup(self):
        self.cleaned = True


def _make(root, installer, nvidia=None, default=None, resetup=False, spawn=None):
    done = []
    win = SetupWindow(
        root,
        app_home="app",
        profile_default=default,
        nvidia=nvidia or {"found": False, "name": "", "driver": ""},
        installer=installer,
        on_done=done.append,
        spawn=spawn or (lambda fn: fn()),
        resetup=resetup,
    )
    return win, done


def _labels(widget):
    out = []
    for w in widget.winfo_children():
        try:
            out.append(str(w.cget("text")))
        except tk.TclError:
            pass
        out.extend(_labels(w))
    return out


def _root_gone(root):
    try:
        root.title()
    except tk.TclError:
        return True
    return False


def test_success_writes_state_and_calls_done(root):
    inst = FakeInstaller([InstallResult(True, True, "")])
    win, done = _make(root, inst, nvidia=GPU)
    win.install_button.invoke()
    root.update()
    assert inst.calls == ["gpu"]
    assert core.read_state()["profile"] == "gpu"
    assert done == ["gpu"]


def test_failure_then_retry_then_success(root):
    inst = FakeInstaller([InstallResult(False, False, "boom"), InstallResult(True, True, "")])
    win, done = _make(root, inst, nvidia=GPU)
    win.install_button.invoke()
    root.update()
    assert core.read_state() is None and not done
    assert win.failure.winfo_manager() == "pack"
    shown = win.failure_text.get("1.0", "end").strip().splitlines()
    assert shown == [f"line {i}" for i in range(10, 40)]  # last 30 lines
    win.retry_button.invoke()
    root.update()
    assert inst.calls == ["gpu", "gpu"]
    assert core.read_state()["profile"] == "gpu"
    assert done == ["gpu"]


def test_installer_exception_is_a_failure(root):
    def bad(profile, log_cb, progress_cb):
        raise RuntimeError("kaput")

    win, done = _make(root, bad)
    win.install_button.invoke()
    root.update()
    assert win.failure.winfo_manager() == "pack" and not done


def test_close_while_installing_waits_for_worker_then_destroys(root, monkeypatch):
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
    pending = []
    inst = FakeInstaller([])
    win, done = _make(root, inst, spawn=pending.append)
    win.install_button.invoke()
    assert win.installing and len(pending) == 1
    win.on_close()
    # the window survives until the worker reports; nothing is deleted on the Tk thread
    assert asked and inst.cancelled and not inst.cleaned
    assert not _root_gone(root)
    pending[0]()  # worker sees the cancel, cleans up itself, finishes
    root.update()
    assert _root_gone(root)
    assert core.read_state() is None and not done


def test_close_wait_is_bounded(root, monkeypatch):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    scheduled = []
    inst = FakeInstaller([])
    win, _ = _make(root, inst, spawn=lambda fn: None)
    win.install_button.invoke()
    real_after = root.after
    monkeypatch.setattr(root, "after", lambda ms, fn=None, *a: scheduled.append(ms) or "x")
    win.on_close()
    assert scheduled == [setup_window.CANCEL_WAIT_MS]
    monkeypatch.setattr(root, "after", real_after)
    win._destroy()  # what the bounded timer does
    assert _root_gone(root)


def test_close_while_installing_declined_keeps_going(root, monkeypatch):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    inst = FakeInstaller([])
    win, _ = _make(root, inst, spawn=lambda fn: None)
    win.install_button.invoke()
    win.on_close()
    assert not inst.cancelled and not _root_gone(root)


def test_close_when_idle_does_not_ask(root):
    win, _ = _make(root, FakeInstaller([]))
    win.on_close()  # askyesno is guarded: an unpatched call would fail the test
    assert _root_gone(root)


def test_late_result_after_close_is_ignored(root, monkeypatch):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    pending = []
    inst = FakeInstaller([InstallResult(True, True, "")])
    win, done = _make(root, inst, spawn=pending.append)
    win.install_button.invoke()
    win.on_close()
    pending[0]()  # worker finishes after the window is gone
    assert not done


def test_gpu_preselected_when_nvidia_found(root):
    win, _ = _make(root, FakeInstaller([]), nvidia=GPU)
    assert win.choice_var.get() == "gpu"
    assert "RTX 4090 detected. About 2.6 GB download, about 5 GB on disk." in _labels(win.choice)


def test_cpu_preselected_without_nvidia_and_warns_on_gpu(root):
    win, _ = _make(root, FakeInstaller([]))
    assert win.choice_var.get() == "cpu"
    assert win.gpu_warning.winfo_manager() == ""
    win.choice_var.set("gpu")
    assert win.gpu_warning.winfo_manager() == "pack"
    assert win.gpu_warning.cget("text") == (
        "No NVIDIA GPU was found — the GPU option may not work on this PC."
    )


def test_state_profile_is_preselected_but_choice_still_shown(root):
    win, _ = _make(root, FakeInstaller([]), nvidia=GPU, default="cpu")
    assert win.choice_var.get() == "cpu"
    assert win.choice.winfo_manager() == "pack"


def test_exact_strings(root):
    win, _ = _make(root, FakeInstaller([]), nvidia=GPU)
    labels = _labels(win.choice)
    assert root.title() == "CampaignScribe — first-time setup"
    assert "GPU (NVIDIA) — recommended" in labels
    assert "CPU only" in labels
    assert "Install" in labels and "Quit" in labels
    assert any(
        "Transcription runs on the CPU and will be much slower for long recordings "
        "(a multi-hour session can take many hours). You can switch to GPU later in Settings." in t
        for t in labels
    )
    assert "Retry" in _labels(win.failure) and "Quit" in _labels(win.failure)
    assert setup_window.CUDA_WARNING == (
        "Installed, but the GPU isn't usable right now (driver missing or too old). "
        "CampaignScribe will use the CPU until that's fixed."
    )
    assert setup_window.CUDA_WARNING in _labels(win.warning)
    assert "Continue" in _labels(win.warning)


def test_low_disk_disables_install(root, monkeypatch):
    monkeypatch.setattr(core, "disk_ok", lambda p, prof: (False, 1024**3))
    inst = FakeInstaller([])
    win, _ = _make(root, inst)
    assert win.install_button.instate(["disabled"])
    assert "Not enough free disk space" in win.error_label.cget("text")
    win.start_install()
    assert inst.calls == [] and not win.installing


def test_long_path_disables_install(root, monkeypatch):
    monkeypatch.setattr(core, "path_ok", lambda p: False)
    win, _ = _make(root, FakeInstaller([]))
    assert win.install_button.instate(["disabled"])
    assert "too long" in win.error_label.cget("text")


def test_resetup_skips_choice_and_starts_immediately(root):
    inst = FakeInstaller([InstallResult(True, True, "")])
    win, done = _make(root, inst, default="cpu", resetup=True)
    assert win.choice.winfo_manager() == ""
    root.update()
    assert inst.calls == ["cpu"]
    assert done == ["cpu"]


def test_cuda_warning_then_continue(root):
    inst = FakeInstaller([InstallResult(True, False, "")])
    win, done = _make(root, inst, nvidia=GPU)
    win.install_button.invoke()
    root.update()
    assert win.warning.winfo_manager() == "pack" and not done
    assert core.read_state()["profile"] == "gpu"
    [b for b in win.warning.winfo_children() if b.winfo_class() == "TButton"][0].invoke()
    assert done == ["gpu"]


def test_cpu_profile_without_cuda_has_no_warning(root):
    inst = FakeInstaller([InstallResult(True, False, "")])
    win, done = _make(root, inst, default="cpu")
    win.install_button.invoke()
    root.update()
    assert done == ["cpu"]


def test_status_line_and_bar(root):
    win, _ = _make(root, FakeInstaller([InstallResult(False, False, "x")]))
    win.install_button.invoke()
    root.update()
    assert win.status_var.get() == "Installing torch (1/4)"
    assert float(win.bar.cget("value")) == 25.0


def test_resetup_blocked_by_disk_shows_only_quit_and_never_installs(root, monkeypatch):
    monkeypatch.setattr(core, "disk_ok", lambda p, prof: (False, 1024**3))
    inst = FakeInstaller([InstallResult(True, True, "")])
    win, done = _make(root, inst, default="cpu", resetup=True)
    root.update()
    assert inst.calls == [] and not done and not win.installing
    assert win.choice.winfo_manager() == "pack"
    assert "Not enough free disk space" in win.error_label.cget("text")
    assert win.gpu_radio.winfo_manager() == "" and win.install_button.winfo_manager() == ""
    assert "Quit" in _labels(win.choice)


def test_resetup_blocked_by_long_path(root, monkeypatch):
    monkeypatch.setattr(core, "path_ok", lambda p: False)
    inst = FakeInstaller([])
    win, _ = _make(root, inst, default="gpu", resetup=True)
    assert inst.calls == [] and "too long" in win.error_label.cget("text")


def test_retry_rechecks_disk_before_starting(root, monkeypatch):
    inst = FakeInstaller([InstallResult(False, False, "boom"), InstallResult(True, True, "")])
    win, done = _make(root, inst, nvidia=GPU)
    win.install_button.invoke()
    root.update()
    monkeypatch.setattr(core, "disk_ok", lambda p, prof: (False, 1024**3))
    win.retry_button.invoke()
    root.update()
    assert inst.calls == ["gpu"] and not done
    assert "Not enough free disk space" in win.failure_label.cget("text")
    monkeypatch.setattr(core, "disk_ok", lambda p, prof: (True, 50 * 1024**3))
    win.retry_button.invoke()
    root.update()
    assert inst.calls == ["gpu", "gpu"] and done == ["gpu"]


class StatusInstaller(FakeInstaller):
    """Reports a scripted sequence of progress calls, then fails (stays on the failure page)."""

    def __init__(self, calls):
        super().__init__([InstallResult(False, False, "x")])
        self.script = calls

    def __call__(self, profile, log_cb, progress_cb):
        for args in self.script:
            progress_cb(*args)
        return self.results.pop(0)


def _status_after(root, calls):
    win, _ = _make(root, StatusInstaller(calls))
    win.install_button.invoke()
    root.update()
    return win.status_var.get()


def test_status_creating_environment(root):
    got = _status_after(root, [(0, 4, None, "Creating the environment\u2026")])
    assert got == "Creating the environment\u2026"


def test_status_updating_pip(root):
    assert _status_after(root, [(0, 4, None, "Updating pip\u2026")]) == "Updating pip\u2026"


def test_status_unpacking_instead_of_freezing_on_last_package(root):
    calls = [
        (3, 4, "torch"),
        (3, 4, None, "Unpacking downloaded packages\u2026 this can take a few minutes"),
        (3, 4, None),  # later log lines (name None) must not erase it
    ]
    got = _status_after(root, calls)
    assert got == "Unpacking downloaded packages\u2026 this can take a few minutes"


def test_plain_package_progress_still_shown(root):
    assert _status_after(root, [(2, 4, "numpy")]) == "Installing numpy (2/4)"


def test_window_sets_icon_when_available(root, monkeypatch):
    calls = []
    monkeypatch.setattr(root, "iconbitmap", lambda path: calls.append(path), raising=False)
    _make(root, FakeInstaller([]))
    from pathlib import Path

    assert [Path(c) for c in calls] == [Path("app") / "assets" / "icon.ico"]


def test_window_survives_icon_failure(root, monkeypatch):
    def boom(path):
        raise tk.TclError("bitmap not defined")

    monkeypatch.setattr(root, "iconbitmap", boom, raising=False)
    win, _ = _make(root, FakeInstaller([]))
    assert win.root is root
