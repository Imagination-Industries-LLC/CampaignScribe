"""fetch_node_runtime: pins, hashing, extraction, and main() exit codes (no network, no exe)."""

from __future__ import annotations

import hashlib
import shutil
import zipfile

from scripts import fetch_node_runtime as fn

TOP = "node-v24.21.0-win-x64"


def _make_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{TOP}/node.exe", b"fake node")
        zf.writestr(f"{TOP}/npm.cmd", b"fake npm")
        zf.writestr(f"{TOP}/node_modules/npm/package.json", b"{}")


def _patch_download(monkeypatch, tmp_path):
    src = tmp_path / "src.zip"
    _make_zip(src)
    monkeypatch.setattr(fn, "download", lambda url, path: shutil.copyfile(src, path))
    return src


def test_pins():
    assert fn.NODE_VERSION == "24.21.0"
    assert fn.ZIP_NAME == "node-v24.21.0-win-x64.zip"
    assert fn.ZIP_SHA256 == "158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541"
    assert fn.URL == "https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip"
    assert fn.DEFAULT_DEST.name == "node"
    assert fn.DEFAULT_DEST.parent.name == "vendor"


def test_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert fn.sha256(p) == hashlib.sha256(b"abc").hexdigest()


def test_is_installed_false_when_files_missing(tmp_path):
    assert fn.is_installed(tmp_path) is False


def test_extract_flattens_top_folder(tmp_path):
    z = tmp_path / "n.zip"
    _make_zip(z)
    dest = tmp_path / "out"
    fn.extract(z, dest)
    assert (dest / "node.exe").read_bytes() == b"fake node"
    assert (dest / "npm.cmd").is_file()
    assert (dest / "node_modules" / "npm" / "package.json").is_file()
    assert not (dest / TOP).exists()


def test_main_installed_skips_download(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "is_installed", lambda dest: True)
    monkeypatch.setattr(fn, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert fn.main(dest=tmp_path) == 0


def test_main_good_download_extracts(tmp_path, monkeypatch):
    src = _patch_download(monkeypatch, tmp_path)
    monkeypatch.setattr(fn, "ZIP_SHA256", fn.sha256(src))
    calls = iter([False, True])
    monkeypatch.setattr(fn, "is_installed", lambda dest: next(calls))
    dest = tmp_path / "vendor" / "node"
    assert fn.main(dest=dest) == 0
    assert (dest / "node.exe").is_file()
    assert not list(dest.parent.glob("*.part"))


def test_main_hash_mismatch_deletes_zip_and_returns_1(tmp_path, monkeypatch, capsys):
    _patch_download(monkeypatch, tmp_path)
    monkeypatch.setattr(fn, "ZIP_SHA256", "0" * 64)
    monkeypatch.setattr(fn, "is_installed", lambda dest: False)
    dest = tmp_path / "vendor" / "node"
    assert fn.main(dest=dest) == 1
    assert "mismatch" in capsys.readouterr().out.lower()
    assert not dest.exists()
    assert not list(tmp_path.glob("vendor/**/*.part"))
    assert not list(tmp_path.glob("vendor/**/*.zip"))


def test_main_network_error_returns_1(tmp_path, monkeypatch, capsys):
    def _boom(url, path):
        raise OSError("no network")

    monkeypatch.setattr(fn, "download", _boom)
    monkeypatch.setattr(fn, "is_installed", lambda dest: False)
    assert fn.main(dest=tmp_path / "vendor" / "node") == 1
    assert "Download failed:" in capsys.readouterr().out
