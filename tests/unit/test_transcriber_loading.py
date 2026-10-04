"""TranscriptionPipeline loads WhisperX with its built-in VAD and diarization from the bundled folder."""

from __future__ import annotations

import inspect
import sys
import types

import pytest

from app.core import models, transcriber


def _make_stubs(tmp_path):
    """Create fake whisperx and whisperx.diarize modules with call tracking."""
    calls = {}

    def fake_load_model(*a, **k):
        calls["load"] = (a, k)
        return object()

    class FakeDiarizationPipeline:
        def __init__(self, **k):
            calls["diarize"] = k

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = fake_load_model

    fake_diar = types.ModuleType("whisperx.diarize")
    fake_diar.DiarizationPipeline = FakeDiarizationPipeline
    fake_wx.diarize = fake_diar

    return fake_wx, fake_diar, calls


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    fake_wx, fake_diar, calls = _make_stubs(tmp_path)
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diar)
    monkeypatch.setattr(models, "diarization_dir", lambda: tmp_path / "weights")
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})
    return calls


def test_constructor_has_no_hf_token():
    assert (
        "hf_token" not in inspect.signature(transcriber.TranscriptionPipeline.__init__).parameters
    )


def test_load_uses_builtin_vad_and_bundled_diarization(stubs, tmp_path):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p._load_models()
    args, kwargs = stubs["load"]
    assert args == ("small", "cpu")
    assert kwargs == {"compute_type": "int8"}  # no vad_method, no use_auth_token
    assert stubs["diarize"] == {
        "model_name": str(tmp_path / "weights"),
        "token": None,
        "device": "cpu",
    }


def test_missing_weights_raise_clear_error(monkeypatch, tmp_path):
    fake_wx, fake_diar, calls = _make_stubs(tmp_path)
    loaded = []

    def tracking_load_model(*a, **k):
        loaded.append(1)
        return object()

    fake_wx.load_model = tracking_load_model
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diar)
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})

    def _missing():
        raise models.MissingModelError("Speaker-diarization model files are missing …")

    monkeypatch.setattr(models, "diarization_dir", _missing)
    with pytest.raises(models.MissingModelError):
        transcriber.TranscriptionPipeline(model_size="small")._load_models()
    assert loaded == []  # failed before the multi-GB Whisper load
