"""Installed / frozen / dev resolution of bundled files (app.core.paths)."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

from app.core import audio, models, notices, paths, privacy

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def clean(monkeypatch):
    monkeypatch.delenv("CAMPAIGNSCRIBE_HOME", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    return monkeypatch


@pytest.fixture
def installed_home(clean, tmp_path):
    home = tmp_path / "inst"
    home.mkdir()
    (home / "main.py").write_text("", encoding="utf-8")
    clean.setenv("CAMPAIGNSCRIBE_HOME", str(home))
    return home


@pytest.fixture
def frozen_home(clean, tmp_path):
    home = tmp_path / "mei"
    home.mkdir()
    clean.setattr(sys, "frozen", True, raising=False)
    clean.setattr(sys, "_MEIPASS", str(home), raising=False)
    return home


@pytest.fixture(params=["installed", "frozen", "dev"])
def layout(request, clean, tmp_path):
    """Yield (mode, expected app_home) for each layout."""
    if request.param == "installed":
        home = tmp_path / "inst"
        home.mkdir()
        (home / "main.py").write_text("", encoding="utf-8")
        clean.setenv("CAMPAIGNSCRIBE_HOME", str(home))
        return "installed", home
    if request.param == "frozen":
        home = tmp_path / "mei"
        home.mkdir()
        clean.setattr(sys, "frozen", True, raising=False)
        clean.setattr(sys, "_MEIPASS", str(home), raising=False)
        return "frozen", home
    return "dev", REPO_ROOT


def test_installed_mode(installed_home):
    assert paths.mode() == "installed"
    assert paths.app_home() == installed_home


def test_frozen_mode(frozen_home):
    assert paths.mode() == "frozen"
    assert paths.app_home() == frozen_home


def test_dev_mode(clean):
    assert paths.mode() == "dev"
    assert paths.app_home() == REPO_ROOT
    assert (paths.app_home() / "main.py").is_file()


def test_installed_wins_over_frozen(installed_home, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "mei"), raising=False)
    assert paths.mode() == "installed"
    assert paths.app_home() == installed_home


def test_stale_home_without_main_py_falls_back_to_dev(clean, tmp_path):
    empty = tmp_path / "gone"
    empty.mkdir()
    clean.setenv("CAMPAIGNSCRIBE_HOME", str(empty))
    assert paths.mode() == "dev"
    assert paths.app_home() == REPO_ROOT


def test_stale_home_falls_back_to_frozen(frozen_home, monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPAIGNSCRIBE_HOME", str(tmp_path / "missing"))
    assert paths.mode() == "frozen"
    assert paths.app_home() == frozen_home


def test_models_root_under_home(layout):
    _, home = layout
    assert models.models_root() == home / "models"


def test_notices_and_privacy_under_home(layout):
    _, home = layout
    assert notices._notices_path() == home / "THIRD-PARTY-NOTICES.md"
    assert privacy._privacy_md_path() == home / "PRIVACY.md"


def test_ffmpeg_under_home_when_bundled(layout):
    mode, home = layout
    if mode == "dev":
        pytest.skip("dev ffmpeg is whatever the checkout has")
    exe = home / "ffmpeg" / "ffmpeg.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    got = Path(audio.get_ffmpeg_path())
    assert got == exe
    assert home in got.parents


def test_ffmpeg_flattened_fallback_when_not_dev(layout):
    mode, home = layout
    if mode == "dev":
        pytest.skip("flattened layout is a bundle-only quirk")
    (home / "ffmpeg.exe").write_bytes(b"")
    assert Path(audio.get_ffmpeg_path()) == home / "ffmpeg.exe"


def test_theme_asset_path_under_home(layout):
    pytest.importorskip("tkinter")
    from app.ui import theme

    _, home = layout
    p = theme._asset_path("fonts", "x.ttf")
    assert p == home / "assets" / "fonts" / "x.ttf"


def test_app_window_asset_dir_under_home(layout):
    pytest.importorskip("tkinter")
    try:
        from app.ui.app_window import AppWindow
    except ImportError:
        pytest.skip("UI dependencies unavailable")

    _, home = layout
    assert Path(AppWindow._asset_dir(None)) == home / "assets"


def test_paths_has_no_writable_location_helper():
    public = {n for n in dir(paths) if not n.startswith("_")}
    for name in public:
        assert not any(w in name.lower() for w in ("data", "write", "cache", "temp", "user"))


def test_app_data_dir_never_under_app_home(installed_home, monkeypatch, tmp_path):
    from app import config

    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("XDG_DATA_HOME", str(appdata))
    monkeypatch.setenv("HOME", str(appdata))
    data_dir = Path(config.get_app_data_dir()).resolve()
    home = paths.app_home().resolve()
    assert home not in data_dir.parents and data_dir != home


def test_app_user_model_id_set_on_windows(monkeypatch):
    main = importlib.import_module("main")
    calls = []
    stub = types.SimpleNamespace(
        windll=types.SimpleNamespace(
            shell32=types.SimpleNamespace(
                SetCurrentProcessExplicitAppUserModelID=lambda s: calls.append(s)
            )
        )
    )
    monkeypatch.setitem(sys.modules, "ctypes", stub)
    monkeypatch.setattr(sys, "platform", "win32")
    main._set_app_user_model_id()
    assert calls == ["ImaginationIndustries.CampaignScribe"]


def test_app_user_model_id_failure_is_swallowed(monkeypatch):
    main = importlib.import_module("main")

    def boom(_):
        raise OSError("nope")

    stub = types.SimpleNamespace(
        windll=types.SimpleNamespace(
            shell32=types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=boom)
        )
    )
    monkeypatch.setitem(sys.modules, "ctypes", stub)
    monkeypatch.setattr(sys, "platform", "win32")
    main._set_app_user_model_id()


def test_app_user_model_id_skipped_off_windows(monkeypatch):
    main = importlib.import_module("main")
    calls = []
    stub = types.SimpleNamespace(
        windll=types.SimpleNamespace(
            shell32=types.SimpleNamespace(
                SetCurrentProcessExplicitAppUserModelID=lambda s: calls.append(s)
            )
        )
    )
    monkeypatch.setitem(sys.modules, "ctypes", stub)
    monkeypatch.setattr(sys, "platform", "linux")
    main._set_app_user_model_id()
    assert calls == []
