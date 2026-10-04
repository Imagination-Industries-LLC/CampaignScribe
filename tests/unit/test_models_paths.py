"""models: locate the bundled diarization weights in a checkout or a frozen build."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core import models


def _populate(root: Path) -> Path:
    d = root / models.DIARIZATION_DIRNAME
    for rel in models.REQUIRED_FILES:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(b"x")
    return d


def test_source_root_is_repo_models():
    assert models.models_root() == Path(models.__file__).resolve().parents[2] / "models"


def test_frozen_root_uses_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert models.models_root() == tmp_path / "models"


def test_diarization_dir_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    d = _populate(tmp_path)
    assert models.diarization_dir() == d


def test_missing_file_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    d = _populate(tmp_path)
    (d / "plda" / "xvec_transform.npz").unlink()
    with pytest.raises(models.MissingModelError) as ei:
        models.diarization_dir()
    assert str(ei.value) == (
        "Speaker-diarization model files are missing from this installation "
        "(plda/xvec_transform.npz). Reinstall CampaignScribe, or in a development "
        "checkout run: python scripts/fetch_diarization_weights.py"
    )


def test_missing_folder_names_every_file(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    with pytest.raises(models.MissingModelError) as ei:
        models.diarization_dir()
    for rel in models.REQUIRED_FILES:
        assert rel in str(ei.value)
