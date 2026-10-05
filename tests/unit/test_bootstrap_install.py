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
