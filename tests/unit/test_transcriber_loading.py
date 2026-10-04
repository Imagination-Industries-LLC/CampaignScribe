"""TranscriptionPipeline loads WhisperX with its built-in VAD and diarization from the bundled folder."""

from __future__ import annotations

import inspect

import pytest

from app.core import models, transcriber


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    import whisperx
    import whisperx.diarize as wd

    calls = {}
    monkeypatch.setattr(
        whisperx, "load_model", lambda *a, **k: calls.setdefault("load", (a, k)) or object()
    )

    class _DP:
        def __init__(self, **k):
            calls["diarize"] = k

    monkeypatch.setattr(wd, "DiarizationPipeline", _DP)
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


def test_missing_weights_raise_clear_error(monkeypatch):
    import whisperx

    monkeypatch.setattr(whisperx, "load_model", lambda *a, **k: object())
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})

    def _missing():
        raise models.MissingModelError("Speaker-diarization model files are missing …")

    monkeypatch.setattr(models, "diarization_dir", _missing)
    with pytest.raises(models.MissingModelError):
        transcriber.TranscriptionPipeline(model_size="small")._load_models()
