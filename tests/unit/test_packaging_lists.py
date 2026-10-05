"""The three dependency lists and the PyInstaller spec all know about the new SDKs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_requirements_list_new_sdks():
    req = _read("requirements.txt")
    assert "\ngoogle-genai\n" in req
    assert "\nopenai\n" in req


def test_setup_venv_installs_new_sdks():
    bat = _read("setup_venv.bat")
    assert "google-genai" in bat and "openai" in bat


def test_pyinstaller_hidden_imports_include_new_sdks():
    bat = _read("build.bat")
    spec = _read("CampaignScribe.spec")
    assert "--hidden-import=google.genai" in bat and "--hidden-import=openai" in bat
    assert "'google.genai'" in spec and "'openai'" in spec


def test_build_fetches_and_bundles_weights_notices_and_privacy():
    bat = _read("build.bat")
    spec = _read("CampaignScribe.spec")
    assert "scripts\\fetch_diarization_weights.py" in bat
    assert bat.index("fetch_diarization_weights") < bat.index("PyInstaller")
    for needle in (
        '--add-data "models\\speaker-diarization-community-1;models\\speaker-diarization-community-1"',
        '--add-data "THIRD-PARTY-NOTICES.md;."',
        '--add-data "PRIVACY.md;."',
    ):
        assert needle in bat, needle
    assert (
        "('models\\\\speaker-diarization-community-1', 'models\\\\speaker-diarization-community-1')"
        in spec
    )
    assert "('THIRD-PARTY-NOTICES.md', '.')" in spec


def test_build_fails_loudly_on_missing_ffmpeg_or_pyinstaller_error():
    bat = _read("build.bat")
    ffmpeg_check = bat.index(r'if not exist "%ROOT%ffmpeg\ffmpeg.exe"')
    pyinstaller = bat.index("-m PyInstaller")
    errorlevel = bat.index("if errorlevel 1", pyinstaller)
    dist_check = bat.index(r'if not exist "dist\CampaignScribe\CampaignScribe.exe"')
    complete = bat.index("Build complete")
    assert ffmpeg_check < pyinstaller
    assert pyinstaller < errorlevel < complete
    assert errorlevel < dist_check < complete


def test_setup_venv_runs_fetch():
    assert "scripts\\fetch_diarization_weights.py" in _read("setup_venv.bat")


def test_build_fetches_node_then_installs_recorder_deps_before_pyinstaller():
    bat = _read("build.bat")
    pyinstaller = bat.index("-m PyInstaller")
    fetch = bat.index("scripts\\fetch_node_runtime.py")
    npm = bat.index('npm.cmd" ci --omit=dev')
    assert fetch < npm < pyinstaller
    assert "pushd recorder" in bat[fetch:npm]
    # each step is followed by an errorlevel check before the next one starts
    assert "if errorlevel 1" in bat[fetch:npm]
    assert "if errorlevel 1" in bat[npm:pyinstaller]


def test_build_bundles_node_and_recorder():
    bat = _read("build.bat")
    spec = _read("CampaignScribe.spec")
    assert '--add-data "vendor\\node\\node.exe;node"' in bat
    assert '--add-data "recorder;recorder"' in bat
    assert "('vendor\\\\node\\\\node.exe', 'node')" in spec
    assert "('recorder', 'recorder')" in spec


def test_setup_venv_fetches_node_runtime():
    assert "scripts\\fetch_node_runtime.py" in _read("setup_venv.bat")


def test_privacy_and_readme_have_no_token():
    for name in ("PRIVACY.md", "README.md"):
        text = _read(name)
        assert "HuggingFace token" not in text and "HF token" not in text, name
    assert "Model downloads (first use only)" in _read("PRIVACY.md")


def test_main_imports_telemetry_off_before_ml_libs():
    import re

    text = _read("main.py")
    pos = text.index("import app.core.telemetry_off")
    first = re.search(r"^\s*(?:import|from)\s+(whisperx|pyannote|torch|app\.ui)\b", text, re.M)
    assert first is None or pos < first.start()
