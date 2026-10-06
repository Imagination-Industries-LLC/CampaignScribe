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
    assert r'"-B ""{app}\bootstrap\launcher.py"""' in ISS
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


def test_bat_is_crlf_and_excludes_python_docs():
    raw = (ROOT / "build_installer.bat").read_bytes()
    assert b"\r\n" in raw  # .gitattributes pins *.bat to CRLF; cmd mis-parses LF-only goto labels
    assert re.search(r"vendor.python.*/XD [^\r\n]*\bDoc\b", BAT)


def test_gitattributes_pins_eol():
    ga = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in ga
    assert "locks/*.txt text eol=lf" in ga


def test_iss_uninstall_deletes_bytecode_dirs():
    assert r'Name: "{app}\app"' in ISS
    assert r'Name: "{app}\bootstrap"' in ISS


def test_bat_precompiles_checked_hash_bytecode_after_staging_before_iscc():
    m = re.search(r"^.*compileall.*$", BAT, re.M)
    assert m, "no compileall step"
    line = m.group(0)
    assert "--invalidation-mode checked-hash" in line
    assert " -B " in line
    for part in (r"%STAGE%\python\Lib", r"%STAGE%\app", r"%STAGE%\bootstrap"):
        assert part in line, part
    assert _pos(r"vendor\python") < m.start() < _pos("ISCC.exe")
    assert "errorlevel 1" in BAT[m.end() : m.end() + 40]


def test_iss_launches_with_dash_B_on_every_entry():
    params = re.findall(r'Parameters: ("(?:[^"]|"")*")', ISS)
    assert len(params) == 3  # two [Icons] shortcuts and the [Run] entry
    for p in params:
        assert p == '"-B ""{app}\\bootstrap\\launcher.py"""', p


def test_iss_uninstall_removes_empty_local_dir_after_env_and_log():
    del_log = ISS.index(
        "DeleteFile(ExpandConstant('{localappdata}\\CampaignScribe\\env-setup.log'))"
    )
    rm = ISS.index("RemoveDir(ExpandConstant('{localappdata}\\CampaignScribe'))")
    assert ISS.index("DelTree(EnvDir, True, True, True)") < del_log < rm


def test_launcher_keeps_dont_write_bytecode_belt_and_braces():
    src = (ROOT / "bootstrap" / "launcher.py").read_text(encoding="utf-8")
    assert src.index("sys.dont_write_bytecode = True") < src.index("from bootstrap import")
