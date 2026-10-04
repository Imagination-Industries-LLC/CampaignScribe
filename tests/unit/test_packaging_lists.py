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


def test_setup_venv_runs_fetch():
    assert "scripts\\fetch_diarization_weights.py" in _read("setup_venv.bat")


def test_privacy_and_readme_have_no_token():
    for name in ("PRIVACY.md", "README.md"):
        text = _read(name)
        assert "HuggingFace token" not in text and "HF token" not in text, name
    assert "Model downloads (first use only)" in _read("PRIVACY.md")
