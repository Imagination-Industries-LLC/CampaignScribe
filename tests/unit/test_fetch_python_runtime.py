"""fetch_python_runtime: pins, hash check, extraction, main() flow (no network)."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import zipfile

import pytest

from scripts import fetch_python_runtime as fp


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("python.exe", "fake exe")
        z.writestr("LICENSE.txt", "PSF")
        z.writestr("Lib/x.py", "x = 1")
    return buf.getvalue()


def test_pins():
    assert fp.PY_VERSION == "3.13.16"
    assert fp.URL == "https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.zip"
    assert fp.ZIP_SHA256 == "bbf675bb5e763c1efbb09a3a461b259d81598a63c30c4b0d7ea11b9f063df159"
    assert fp.DEFAULT_DEST.name == "python"
    assert fp.DEFAULT_DEST.parent.name == "vendor"


def test_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert fp.sha256(p) == hashlib.sha256(b"abc").hexdigest()


def test_is_installed_false_without_python_exe(tmp_path):
    assert fp.is_installed(tmp_path) is False


def test_is_installed_checks_version_and_no_window(tmp_path):
    (tmp_path / "python.exe").write_bytes(b"x")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout="3.13.16\n", stderr="")

    assert fp.is_installed(tmp_path, run=fake_run) is True
    assert "tkinter" in seen["cmd"][-1]
    if sys.platform == "win32":
        assert seen["kw"]["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_is_installed_wrong_version_or_failure(tmp_path):
    (tmp_path / "python.exe").write_bytes(b"x")
    wrong = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="3.12.1\n")  # noqa: E731
    assert fp.is_installed(tmp_path, run=wrong) is False

    def boom(cmd, **kw):
        raise OSError("nope")

    assert fp.is_installed(tmp_path, run=boom) is False


def test_https_guard():
    with pytest.raises(ValueError):
        fp.download("http://example.com/x.zip", __import__("pathlib").Path("x.part"))


def test_main_already_installed_skips_download(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "is_installed", lambda dest, **k: True)
    monkeypatch.setattr(fp, "download", lambda *a, **k: pytest.fail("must not download"))
    assert fp.main([], dest=tmp_path) == 0


def test_main_downloads_verifies_extracts(tmp_path, monkeypatch):
    data = _zip_bytes()
    monkeypatch.setattr(fp, "ZIP_SHA256", hashlib.sha256(data).hexdigest())
    state = {"n": 0}

    def fake_installed(dest, **k):
        state["n"] += 1
        return state["n"] > 1  # false first, true after extraction

    monkeypatch.setattr(fp, "is_installed", fake_installed)
    monkeypatch.setattr(fp, "download", lambda url, part: part.write_bytes(data))
    dest = tmp_path / "python"
    assert fp.main([], dest=dest) == 0
    assert (dest / "python.exe").read_text() == "fake exe"
    assert (dest / "Lib" / "x.py").is_file()
    assert not list(tmp_path.glob("*.part"))


def test_main_hash_mismatch_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "is_installed", lambda dest, **k: False)
    monkeypatch.setattr(fp, "download", lambda url, part: part.write_bytes(b"tampered"))
    dest = tmp_path / "python"
    assert fp.main([], dest=dest) == 1
    assert not (dest / "python.exe").exists()
    assert not list(tmp_path.glob("*.part"))


def test_main_download_failure_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "is_installed", lambda dest, **k: False)

    def fail(url, part):
        raise OSError("offline")

    monkeypatch.setattr(fp, "download", fail)
    assert fp.main([], dest=tmp_path / "python") == 1
