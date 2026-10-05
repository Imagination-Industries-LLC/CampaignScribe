"""Static checks on build_installer.bat and installer/CampaignScribe.iss (Linux-safe)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BAT = (ROOT / "build_installer.bat").read_text(encoding="utf-8")
ISS = (ROOT / "installer" / "CampaignScribe.iss").read_text(encoding="utf-8")


def _pos(needle: str) -> int:
    i = BAT.find(needle)
    assert i >= 0, needle
    return i


def test_bat_step_order():
    order = [
        "fetch_diarization_weights.py",
        "fetch_python_runtime.py",
        "robocopy",
        r"app\__init__.py",
        "ISCC",
        "dist-installer",
    ]
    positions = [_pos(s) for s in order]
    assert positions == sorted(positions)


def test_bat_checks_errorlevel_after_each_step():
    assert len(re.findall(r"errorlevel 1", BAT)) >= 5
    assert "errorlevel 8" in BAT  # robocopy: 0-7 are success codes
    assert "exit /b 1" in BAT


def test_bat_assembles_bootstrap_locks_and_python():
    for item in ("bootstrap", "locks", "assets", "ffmpeg", "speaker-diarization-community-1"):
        assert item in BAT, item
    for f in ("LICENSE", "PRIVACY.md", "THIRD-PARTY-NOTICES.md", "main.py"):
        assert f in BAT, f
    assert r"vendor\python" in BAT
    assert "__pycache__" in BAT


def test_bat_recorder_only_when_lockfile_tracked():
    assert "git ls-files recorder/package-lock.json" in BAT
    assert r"recorder\test" in BAT
    assert "HAVE_RECORDER" in BAT


def test_bat_iscc_search_and_hint():
    assert "%INNO_SETUP%" in BAT
    assert r"Inno Setup 6\ISCC.exe" in BAT
    assert "Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or set INNO_SETUP." in BAT
    assert "/DAppVersion=" in BAT


def test_iss_invariants():
    for line in (
        "PrivilegesRequired=lowest",
        "PrivilegesRequiredOverridesAllowed=dialog",
        r"DefaultDirName={autopf}\CampaignScribe",
        "AppPublisher=Imagination Industries LLC",
        "LicenseFile=LICENSE",
        "InfoBeforeFile=PRIVACY.md",
        "CloseApplications=yes",
    ):
        assert line in ISS, line
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}$", ISS, re.M)
    assert 'AppUserModelID: "ImaginationIndustries.CampaignScribe"' in ISS
    assert r"{app}\python\pythonw.exe" in ISS
    assert r'"""{app}\bootstrap\launcher.py"""' in ISS
    assert "nowait postinstall skipifsilent" in ISS
    assert r"build\installer-root\*" in ISS and "recursesubdirs" in ISS


def test_iss_uninstall_prompt_and_user_data_safe():
    assert "Also remove the downloaded speech engine (about " in ISS
    assert r"%LOCALAPPDATA%\CampaignScribe)?" in ISS
    assert r"{localappdata}\CampaignScribe\env" in ISS
    assert "env-setup.log" in ISS
    assert "usPostUninstall" in ISS
    assert "DelTree(EnvDir, True, True, True)" in ISS
    # user data is never deleted
    assert "DelTree(ExpandConstant('{userappdata}" not in ISS
    assert not re.search(r"(?:DelTree|DeleteFile)\([^)]*userappdata", ISS)
