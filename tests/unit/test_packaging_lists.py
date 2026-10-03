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
