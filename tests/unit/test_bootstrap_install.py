import os
import subprocess
import sys
import threading
import time

import pytest

from bootstrap import core, install


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = tmp_path / "app"
    (app / "locks").mkdir(parents=True)
    lock = (
        "# header\n# pip==26.2.1\n--extra-index-url https://x/cpu\n\n"
        "torch==2.5.1+cpu\nnumpy==2.0.0\n"
    )
    (app / "locks" / "cpu.txt").write_text(lock, encoding="utf-8", newline="\n")
    (app / "locks" / "gpu.txt").write_text(lock, encoding="utf-8", newline="\n")
    return app


class FakeRun:
    def __init__(self, fail_at=None, verify_out="2.5.1 False", raise_at=None):
        self.cmds = []
        self.fail_at = fail_at
        self.raise_at = raise_at
        self.verify_out = verify_out
        self.timeouts = []
        self.snapshots = []

    def __call__(self, cmd, line_cb, timeout=None):
        idx = len(self.cmds)
        self.cmds.append([str(c) for c in cmd])
        self.timeouts.append(timeout)
        self.snapshots.append((core.read_state(), core.env_dir().exists()))
        if idx == self.raise_at:
            raise OSError("disk gone")
        if idx == 2:
            for line in ("Collecting torch==2.5.1+cpu", "Collecting numpy==2.0.0"):
                line_cb(line)
        if idx == self.fail_at:
            return 1, "bad"
        if idx == 3:
            return 0, self.verify_out
        return 0, ""


def _stale_env():
    core.env_dir().mkdir(parents=True)
    (core.env_dir() / "junk.txt").write_text("x")
    core.write_state("cpu", "oldsha", "3.13.16")


def _run(home, run, profile="cpu"):
    inst = install.Installer(home, run=run, base_python="BASE")
    return inst(profile, lambda s: None, lambda *a: None)


def test_count_lock_lines_excludes_comments_and_options(home):
    assert install.count_lock_lines(core.lock_path(home, "cpu")) == 2


def test_package_name_strips_version():
    assert install.package_name("torch==2.5.1+cu124") == "torch"
    assert install.package_name("numpy") == "numpy"


def test_sequence_and_success(home):
    run = FakeRun()
    logs, prog = [], []
    inst = install.Installer(home, run=run, base_python="BASE")
    res = inst("cpu", logs.append, lambda *a: prog.append(a))
    assert res == install.InstallResult(True, False, "")
    venv, upgrade, pipi, verify = run.cmds
    assert venv == ["BASE", "-m", "venv", str(core.env_dir())]
    assert upgrade[1:3] == ["-m", "pip"] and "pip==26.2.1" in upgrade
    assert "--no-deps" in pipi and "-r" in pipi and pipi[-1].endswith("cpu.txt")
    assert verify[1] == "-c"
    assert run.timeouts[3] == install.VERIFY_TIMEOUT
    state = core.read_state()
    assert state["profile"] == "cpu"
    assert state["lock_sha256"] == core.lock_sha256(core.lock_path(home, "cpu"))
    assert (1, 2, "torch") in prog and prog[-1] == (2, 2, None)
    assert core.setup_log_path().read_text(encoding="utf-8")


@pytest.mark.parametrize("fail_at", [0, 1, 2, 3])
def test_stops_at_first_failure_and_writes_no_state(home, fail_at):
    run = FakeRun(fail_at=fail_at)
    res = _run(home, run)
    assert not res.ok and "failed" in res.message
    assert len(run.cmds) == fail_at + 1
    assert core.read_state() is None


@pytest.mark.parametrize("out", ["", "garbage", "2.5.1 maybe"])
def test_unparseable_verify_is_failure(home, out):
    res = _run(home, FakeRun(verify_out=out))
    assert not res.ok and core.read_state() is None


def test_cuda_ok_reported(home):
    res = _run(home, FakeRun(verify_out="2.5.1+cu124 True"), "gpu")
    assert res.ok and res.cuda_ok


def test_state_deleted_before_env_mutation(home):
    _stale_env()
    run = FakeRun()
    _run(home, run)
    # at the first command (venv) the old state and stale env are already gone
    assert run.snapshots[0] == (None, False)


def test_interrupted_install_never_looks_complete(home):
    _stale_env()
    res = _run(home, FakeRun(raise_at=2))  # crash mid pip install, after state deletion
    assert not res.ok
    assert core.read_state() is None
    assert core.decide(core.read_state(), home, False, None) == ("setup", None)
    assert core.decide(core.read_state(), home, True, None) == ("setup", None)


def test_cancel_stops_install_and_cleanup_removes_env(home):
    inst = install.Installer(home, base_python="b")

    def run(cmd, line_cb, timeout=None):
        inst.cancel()
        return 1, ""

    inst._run = run
    res = inst("cpu", lambda s: None, lambda *a: None)
    assert not res.ok and res.message == "Cancelled"
    _stale_env()
    inst.cleanup()
    assert not core.env_dir().exists()


def test_base_python_falls_back_in_dev_checkout(home, monkeypatch):
    monkeypatch.setattr(install.sys, "executable", str(home / "venv" / "Scripts" / "pythonw.exe"))
    assert install.Installer(home).base_python() == home / "venv" / "Scripts" / "python.exe"
    (home / "python").mkdir()
    (home / "python" / "python.exe").write_text("")
    assert install.Installer(home).base_python() == home / "python" / "python.exe"


def test_cancel_between_steps_runs_no_later_step_and_no_state(home):
    inst = install.Installer(home, base_python="b")
    cmds = []

    def run(cmd, line_cb, timeout=None):
        cmds.append(cmd)
        if len(cmds) == 2:  # cancel lands after the pip upgrade returns 0
            inst.cancel()
        return 0, ""

    inst._run = run
    res = inst("cpu", lambda s: None, lambda *a: None)
    assert len(cmds) == 2 and res.message.startswith("Cancelled")
    assert core.read_state() is None and not core.env_dir().exists()


def test_cancel_after_verify_before_write_state_writes_nothing(home):
    inst = install.Installer(home, base_python="b")
    n = []

    def run(cmd, line_cb, timeout=None):
        n.append(1)
        if len(n) == 4:  # verify succeeds, and cancel arrives right after
            inst.cancel()
            return 0, "2.5.1 True"
        return 0, ""

    inst._run = run
    res = inst("cpu", lambda s: None, lambda *a: None)
    assert not res.ok and res.message.startswith("Cancelled")
    assert core.read_state() is None


def test_cleanup_reports_leftover_when_locked(home, monkeypatch):
    core.env_dir().mkdir(parents=True)
    monkeypatch.setattr(install.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(install.time, "sleep", lambda s: None)
    inst = install.Installer(home, base_python="b")
    assert inst.cleanup(attempts=3) == str(core.env_dir())


def test_missing_base_python_message(home):
    inst = install.Installer(home, base_python=str(home / "nope" / "python.exe"))
    res = inst("cpu", lambda s: None, lambda *a: None)
    assert not res.ok and "Python runtime not found at" in res.message


# --- the real runner ---------------------------------------------------------


def test_stream_run_streams_lines_and_sets_env(home):
    inst = install.Installer(home, base_python="b")
    lines = []
    code = (
        "import os; print('a'); print('b'); "
        "print(os.environ['PIP_NO_INPUT'], os.environ['PYTHONIOENCODING'], "
        "os.environ['PYTHONDONTWRITEBYTECODE'])"
    )
    rc, out = inst._stream_run([sys.executable, "-c", code], lines.append)
    assert rc == 0 and lines == ["a", "b", "1 utf-8 1"] and out == "\n".join(lines)


def test_stream_run_nonzero_exit(home):
    inst = install.Installer(home, base_python="b")
    rc, _ = inst._stream_run([sys.executable, "-c", "import sys; sys.exit(3)"], lambda s: None)
    assert rc == 3


_PARENT = (
    "import subprocess, sys, time\n"
    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(g.pid, flush=True)\n"
    "time.sleep(60)\n"
)


def _alive(pid):
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
        ).stdout
        return str(pid) in out
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_dead(pid, limit=8.0):
    end = time.time() + limit
    while time.time() < end:
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree kill")
def test_stream_run_timeout_kills_whole_tree(home):
    inst = install.Installer(home, base_python="b")
    pids = []
    t0 = time.time()
    rc, _ = inst._stream_run([sys.executable, "-c", _PARENT], lambda s: pids.append(s), timeout=2)
    assert rc != 0 and time.time() - t0 < 20
    if sys.platform == "win32":  # tree kill is the Windows redirector fix
        assert _wait_dead(int(pids[0]))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree kill")
def test_cancel_kills_whole_tree_and_read_loop_returns(home):
    inst = install.Installer(home, base_python="b")
    pids = []
    started = threading.Event()

    def cb(line):
        pids.append(line)
        started.set()

    result = {}
    th = threading.Thread(
        target=lambda: result.update(r=inst._stream_run([sys.executable, "-c", _PARENT], cb))
    )
    th.start()
    assert started.wait(15)
    inst.cancel()
    th.join(15)
    assert not th.is_alive()
    if sys.platform == "win32":
        assert _wait_dead(int(pids[0]))


def test_cancel_before_call_is_not_lost(home):
    inst = install.Installer(home, base_python="b")
    cmds = []
    inst._run = lambda cmd, line_cb, timeout=None: cmds.append(cmd) or (0, "")
    inst.cancel()  # lands after spawn, before the worker's __call__
    res = inst("cpu", lambda s: None, lambda *a: None)
    assert cmds == [] and not res.ok and res.message.startswith("Cancelled")
    assert core.read_state() is None
    inst.reset()  # the window does this before spawning the next attempt
    assert inst._cancelled is False


def test_cancel_during_write_state_is_atomic(home, monkeypatch):
    inst = install.Installer(home, base_python="b")
    inst._run = FakeRun()
    real = core.write_state
    started = threading.Event()
    th = []

    def racing_write(*a):
        t = threading.Thread(target=lambda: (started.set(), inst.cancel()))
        t.start()
        th.append(t)
        started.wait(5)
        t.join(0.3)
        assert t.is_alive()  # cancel() is blocked on the lock while state is written
        real(*a)

    monkeypatch.setattr(core, "write_state", racing_write)
    res = inst("cpu", lambda s: None, lambda *a: None)
    th[0].join(5)
    assert res.ok and core.read_state() is not None  # never "cancelled but state exists"


def test_taskkill_uses_full_system32_path(monkeypatch):
    monkeypatch.setenv("SystemRoot", "C:\\Win")
    assert install._taskkill_exe() == os.path.join("C:\\Win", "System32", "taskkill.exe")
    monkeypatch.delenv("SystemRoot")
    assert install._taskkill_exe() == os.path.join(r"C:\Windows", "System32", "taskkill.exe")


def test_kill_tree_runs_full_path_taskkill(monkeypatch):
    seen = []
    monkeypatch.setattr(install.sys, "platform", "win32")
    monkeypatch.setattr(install.subprocess, "run", lambda cmd, **k: seen.append(cmd))
    monkeypatch.setattr(install, "_taskkill_exe", lambda: "FULL")

    class P:
        pid = 42

        def kill(self):
            pass

    install._kill_tree(P())
    assert seen == [["FULL", "/T", "/F", "/PID", "42"]]


def test_step_status_and_unpacking_notices(home):
    class Run(FakeRun):
        def __call__(self, cmd, line_cb, timeout=None):
            if len(self.cmds) == 2:
                line_cb("Collecting torch==2.5.1+cpu")
                line_cb("Installing collected packages: torch, numpy")
            return super().__call__(cmd, line_cb, timeout)

    prog = []
    inst = install.Installer(home, run=Run(), base_python="BASE")
    inst("cpu", lambda s: None, lambda *a: prog.append(a))
    statuses = [a[3] for a in prog if len(a) == 4]
    assert statuses == [
        install.STATUS_CREATING,
        install.STATUS_PIP,
        install.STATUS_UNPACKING,
    ]
    assert install.STATUS_CREATING == "Creating the environment\u2026"
    assert install.STATUS_PIP == "Updating pip\u2026"
    assert install.STATUS_UNPACKING.startswith("Unpacking downloaded packages")
