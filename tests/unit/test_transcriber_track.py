"""TranscriptionPipeline.transcribe_track: one speaker per track, optional diarization."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from app.core import models, transcriber


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    diarize_calls: list[dict] = []
    state = SimpleNamespace(diarize_calls=diarize_calls, load_model_calls=0)

    class FakeModel:
        def transcribe(self, path, batch_size=16):
            return {
                "language": "en",
                "segments": [{"start": 0.0, "end": 1.0, "text": " hi "}],
            }

    def fake_load_model(*a, **k):
        state.load_model_calls += 1
        return FakeModel()

    class FakeDiarizationPipeline:
        def __init__(self, **k):
            pass

        def __call__(self, path, **k):
            diarize_calls.append(k)
            if k.get("return_embeddings"):
                return "DIAR", {"SPEAKER_00": [0.1, 0.2]}
            return "DIAR"

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = fake_load_model
    fake_wx.load_align_model = lambda **k: (object(), {})
    fake_wx.align = lambda segs, *a: {"segments": segs}
    fake_wx.assign_word_speakers = lambda diar, result: {
        "segments": [dict(s, speaker="SPEAKER_01") for s in result["segments"]]
    }
    fake_diar = types.ModuleType("whisperx.diarize")
    fake_diar.DiarizationPipeline = FakeDiarizationPipeline
    fake_wx.diarize = fake_diar

    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diar)
    monkeypatch.setattr(models, "diarization_dir", lambda: tmp_path)
    monkeypatch.setattr(transcriber, "check_gpu", lambda: {"cuda_available": False})
    monkeypatch.setattr(transcriber, "coerce_embeddings", lambda raw: dict(raw or {}))
    return state


def test_track_without_diarize_never_calls_pyannote(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    segs = p.transcribe_track("x.wav")
    assert segs == [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00"}]
    assert fakes.diarize_calls == []
    assert p._last_speaker_embeddings == {}


def test_track_with_diarize_matches_transcribe_file(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    a = p.transcribe_track("x.wav", diarize=True, min_speakers=2, max_speakers=3)
    b = p.transcribe_file("x.wav", min_speakers=2, max_speakers=3)
    assert a == b == [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_01"}]
    assert fakes.diarize_calls[0]["min_speakers"] == 2


def test_embeddings_reset_between_tracks(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p.transcribe_track("x.wav", diarize=True)
    assert p._last_speaker_embeddings  # set by the diarized track
    p.transcribe_track("y.wav")
    assert p._last_speaker_embeddings == {}


def test_models_load_once_across_tracks(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")
    p.transcribe_track("x.wav")
    p.transcribe_track("y.wav")
    assert fakes.load_model_calls == 1


def test_progress_can_cancel(fakes):
    p = transcriber.TranscriptionPipeline(model_size="small")

    def cb(stage, pct):
        if stage == "Transcribing":
            raise InterruptedError("Cancelled")

    with pytest.raises(InterruptedError):
        p.transcribe_track("x.wav", progress=cb)
