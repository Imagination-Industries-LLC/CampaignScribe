import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bootstrap import core

REPO = Path(__file__).resolve().parents[2]
EXCERPT = Path(__file__).with_name("pip_install_excerpt.txt")


@pytest.fixture
def local_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


def _make_home(tmp_path, gpu="gpu lock\n", cpu="# pip==26.2.1\ncpu lock\n"):
    home = tmp_path / "app"
    (home / "locks").mkdir(parents=True)
    (home / "locks" / "gpu.txt").write_text(gpu, encoding="utf-8", newline="\n")
    (home / "locks" / "cpu.txt").write_text(cpu, encoding="utf-8", newline="\n")
    return home


# --- paths / state ---------------------------------------------------------


def test_paths_under_localappdata(local_appdata):
    assert core.env_dir() == local_appdata / "CampaignScribe" / "env"
    assert core.state_path() == core.env_dir() / "cs-setup.json"
    assert core.setup_log_path() == local_appdata / "CampaignScribe" / "env-setup.log"


def test_state_roundtrip_and_no_temp_left(local_appdata):
    assert core.read_state() is None
    core.write_state("gpu", "abc", "3.13.16")
    assert core.read_state() == {
        "profile": "gpu",
        "lock_sha256": "abc",
        "python_version": "3.13.16",
    }
    assert [p.name for p in core.env_dir().iterdir()] == ["cs-setup.json"]
    assert not core.state_path().read_bytes().startswith(b"\xef\xbb\xbf")


def test_write_state_overwrites(local_appdata):
    core.write_state("gpu", "a", "3.13.16")
    core.write_state("cpu", "b", "3.13.16")
    assert core.read_state()["profile"] == "cpu"


@pytest.mark.parametrize("content", ["{not json", "", "[1, 2]", '"str"'])
def test_corrupt_state_is_none(local_appdata, content):
    core.env_dir().mkdir(parents=True)
    core.state_path().write_text(content, encoding="utf-8")
    assert core.read_state() is None


# --- lock files ------------------------------------------------------------


def test_lock_path(tmp_path):
    assert core.lock_path(tmp_path, "cpu") == tmp_path / "locks" / "cpu.txt"


def test_lock_sha256_parity_with_make_locks(tmp_path):
    sys.path.insert(0, str(REPO))
    try:
        from scripts import make_locks
    finally:
        sys.path.remove(str(REPO))
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"# pip==1\na==1\nb==2\n")
    crlf.write_bytes(b"# pip==1\r\na==1\r\nb==2\r\n")
    assert core.lock_sha256(lf) == make_locks.lock_sha256(lf)
    assert core.lock_sha256(crlf) == make_locks.lock_sha256(crlf)
    assert core.lock_sha256(lf) == core.lock_sha256(crlf)


def test_lock_pip_version(tmp_path):
    f = tmp_path / "l.txt"
    f.write_text("# CampaignScribe cpu lock\n# pip==26.2.1\nx==1\n", encoding="utf-8")
    assert core.lock_pip_version(f) == "26.2.1"
    f.write_text("x==1\n", encoding="utf-8")
    assert core.lock_pip_version(f) is None
    assert core.lock_pip_version(tmp_path / "missing.txt") is None


def test_real_locks_have_pip_version():
    for p in ("gpu", "cpu"):
        assert core.lock_pip_version(core.lock_path(REPO, p))


# --- decide ----------------------------------------------------------------


def _state(home, profile, sha=None):
    return {
        "profile": profile,
        "lock_sha256": sha or core.lock_sha256(core.lock_path(home, profile)),
    }


def test_decide_no_state_is_setup_without_default(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide(None, home, True, None) == ("setup", None)


def test_decide_invalid_state_is_setup(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide({"profile": "tpu"}, home, True, None) == ("setup", None)
    assert core.decide({}, home, True, None) == ("setup", None)


def test_decide_launch(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide(_state(home, "gpu"), home, True, None) == ("launch", "gpu")


def test_decide_missing_env_python_is_setup_with_profile_default(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide(_state(home, "cpu"), home, False, None) == ("setup", "cpu")


def test_decide_lock_changed_is_resetup_same_profile(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide(_state(home, "gpu", "stale"), home, True, None) == ("resetup", "gpu")


def test_decide_missing_bundled_lock_is_resetup(tmp_path):
    home = _make_home(tmp_path)
    st = _state(home, "gpu")
    core.lock_path(home, "gpu").unlink()
    assert core.decide(st, home, True, None) == ("resetup", "gpu")


def test_decide_switch_wins(tmp_path):
    home = _make_home(tmp_path)
    assert core.decide(_state(home, "gpu"), home, True, "cpu") == ("setup", "cpu")
    assert core.decide(None, home, False, "gpu") == ("setup", "gpu")


# --- nvidia ----------------------------------------------------------------


def _run_returning(stdout="", returncode=0, exc=None, seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.append((cmd, kw))
        if exc:
            raise exc
        return SimpleNamespace(stdout=stdout, returncode=returncode)

    return run


def test_detect_nvidia_found():
    seen = []
    run = _run_returning("NVIDIA GeForce RTX 4090, 560.94\n", seen=seen)
    got = core.detect_nvidia(run=run, which=lambda _: "C:/x/nvidia-smi.exe")
    assert got == {"found": True, "name": "NVIDIA GeForce RTX 4090", "driver": "560.94"}
    cmd, kw = seen[0]
    assert "--query-gpu=name,driver_version" in cmd and "--format=csv,noheader" in cmd
    assert kw["timeout"] == 10
    expected = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    assert kw["creationflags"] == expected


def test_detect_nvidia_multi_gpu_uses_first():
    run = _run_returning("GPU A, 1.0\nGPU B, 1.0\n")
    assert core.detect_nvidia(run=run, which=lambda _: "x")["name"] == "GPU A"


def test_detect_nvidia_not_on_path_or_system32(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    run = _run_returning("x, y")
    assert core.detect_nvidia(run=run, which=lambda _: None)["found"] is False


def test_detect_nvidia_system32_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    (tmp_path / "System32").mkdir()
    (tmp_path / "System32" / "nvidia-smi.exe").write_bytes(b"")
    seen = []
    run = _run_returning("Card, 551.1", seen=seen)
    assert core.detect_nvidia(run=run, which=lambda _: None)["found"] is True
    assert seen[0][0][0].endswith("nvidia-smi.exe")


def test_detect_nvidia_timeout():
    run = _run_returning(exc=subprocess.TimeoutExpired("nvidia-smi", 10))
    assert core.detect_nvidia(run=run, which=lambda _: "x")["found"] is False


def test_detect_nvidia_oserror():
    run = _run_returning(exc=OSError("boom"))
    assert core.detect_nvidia(run=run, which=lambda _: "x")["found"] is False


def test_detect_nvidia_nonzero_exit():
    run = _run_returning("NVIDIA-SMI has failed", returncode=9)
    assert core.detect_nvidia(run=run, which=lambda _: "x")["found"] is False


def test_detect_nvidia_empty_output():
    run = _run_returning("\n  \n")
    assert core.detect_nvidia(run=run, which=lambda _: "x")["found"] is False


def test_detect_nvidia_odd_output_without_comma():
    run = _run_returning("Weird Card\n")
    assert core.detect_nvidia(run=run, which=lambda _: "x") == {
        "found": True,
        "name": "Weird Card",
        "driver": "",
    }


# --- disk / path -----------------------------------------------------------


def test_required_bytes():
    gib = 1024**3
    assert core.required_bytes("gpu") == 8 * gib
    assert core.required_bytes("cpu") == int(1.6 * gib) + 2 * gib


def test_disk_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: SimpleNamespace(free=10 * 1024**3))
    target = tmp_path / "does" / "not" / "exist"
    assert core.disk_ok(target, "gpu") == (True, 10 * 1024**3)
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: SimpleNamespace(free=7 * 1024**3))
    assert core.disk_ok(target, "gpu") == (False, 7 * 1024**3)
    assert core.disk_ok(target, "cpu")[0] is True


def test_path_ok_limit():
    assert core.path_ok("x" * 80) is True
    assert core.path_ok("x" * 81) is False
    assert core.path_ok(Path("C:/Users/a/AppData/Local/CampaignScribe/env")) is True


# --- commands --------------------------------------------------------------


def test_pip_command_flags():
    cmd = core.pip_command("py.exe", "lock.txt")
    assert cmd[:4] == ["py.exe", "-m", "pip", "install"]
    for flag in ("--no-deps", "--require-virtualenv", "--disable-pip-version-check"):
        assert flag in cmd
    assert cmd[cmd.index("--progress-bar") + 1] == "off"
    assert cmd[cmd.index("--retries") + 1] == "5"
    assert cmd[cmd.index("--timeout") + 1] == "60"
    assert cmd[-2:] == ["-r", "lock.txt"]


def test_pip_upgrade_command():
    assert core.pip_upgrade_command("py", "26.2.1")[-1] == "pip==26.2.1"


def test_verify_command_and_parse():
    cmd = core.verify_command("py.exe")
    assert cmd[:2] == ["py.exe", "-c"]
    assert "torch.cuda.is_available()" in cmd[2] and "faster_whisper" in cmd[2]
    assert core.parse_verify("2.8.0+cu128 True\n") == ("2.8.0+cu128", True)
    assert core.parse_verify("warning: x\n2.8.0+cpu False\r\n") == ("2.8.0+cpu", False)
    for bad in ("", "garbage", "1.0 maybe"):
        with pytest.raises(ValueError):
            core.parse_verify(bad)


def test_launch_command_sets_home():
    cmd, env = core.launch_command(Path("e/pythonw.exe"), Path("app"), base_env={"A": "1"})
    assert cmd == [str(Path("e/pythonw.exe")), str(Path("app") / "main.py")]
    assert env == {"A": "1", "CAMPAIGNSCRIBE_HOME": "app", "PYTHONDONTWRITEBYTECODE": "1"}


# --- progress --------------------------------------------------------------


def test_progress_counter_on_pip_excerpt():
    counter = core.ProgressCounter(3)
    seen = [counter.feed(ln) for ln in EXCERPT.read_text(encoding="utf-8").splitlines()]
    names = [s[2] for s in seen if s[2]]
    assert names == ["aiohappyeyeballs==2.7.1", "numpy==2.3.3", "torch==2.8.0+cpu"]
    dones = [s[0] for s in seen]
    assert dones == sorted(dones)
    # held below full until pip reports success
    assert max(s[0] for s in seen[:-1]) == 2
    assert seen[-1][:2] == (3, 3)


def test_progress_counter_download_lines_do_not_advance():
    c = core.ProgressCounter(10)
    c.feed("Collecting a==1")
    assert c.feed("  Downloading a-1.whl (1 MB)")[0] == 1
    assert c.feed("  Using cached a-1.whl")[0] == 1


def test_progress_counter_never_exceeds_total():
    c = core.ProgressCounter(2)
    for _ in range(5):
        done, total, _ = c.feed("Collecting x==1")
    assert done < total
    assert c.feed("Successfully installed x-1")[:2] == (2, 2)
