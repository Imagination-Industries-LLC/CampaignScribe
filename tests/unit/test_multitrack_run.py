"""transcribe_tracks: per-track transcription, relabel, merge, failures, cancel."""

from __future__ import annotations

import os

import pytest

from app.core import multitrack as mt


def _orig(wav: str) -> str:
    """Temp wav 'x/a.flac.tmp.wav' -> original track name 'a.flac'."""
    return os.path.basename(wav)[: -len(".tmp.wav")]


class FakePipeline:
    def __init__(self, canned, fail=(), diar_emb=None):
        self.canned = canned  # original file name -> list of (start, text, speaker)
        self.fail = set(fail)  # original file names that raise
        self.diar_emb = diar_emb or {}
        self.calls = []
        self._last_speaker_embeddings = {}

    def transcribe_track(self, wav, *, diarize=False, progress=None, **kw):
        name = _orig(wav)
        self.calls.append((name, diarize, kw))
        self._last_speaker_embeddings = {}
        if progress:
            progress("Transcribing", 0.2)
        if name in self.fail:
            raise RuntimeError("bad audio")
        if diarize:
            self._last_speaker_embeddings = dict(self.diar_emb)
        return [
            {"start": s, "end": s + 1, "text": t, "speaker": spk if diarize else "SPEAKER_00"}
            for s, t, spk in self.canned.get(name, [])
        ]


@pytest.fixture
def wav_for(tmp_path, monkeypatch):
    made = []

    def _wav_for(track):
        p = tmp_path / (os.path.basename(track.path) + ".tmp.wav")
        p.write_bytes(b"x")
        made.append(str(p))
        return str(p)

    monkeypatch.setattr(mt, "wav_duration", lambda p: 60.0)
    _wav_for.made = made
    return _wav_for


def _tracks():
    return [mt.Track("a.flac", "Mike"), mt.Track("b.flac", "Sarah")]


def test_relabel_merge_and_mapping(wav_for):
    pipe = FakePipeline(
        {"a.flac": [(5.0, "a2", None), (1.0, "a1", None)], "b.flac": [(2.0, "b1", None)]}
    )
    res = mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for)
    assert [(s["text"], s["speaker"]) for s in res.segments] == [
        ("a1", "TRACK_01"),
        ("b1", "TRACK_02"),
        ("a2", "TRACK_01"),
    ]
    assert res.mapping == {"TRACK_01": "Mike", "TRACK_02": "Sarah"}
    assert res.failures == {}
    assert res.durations == {"a.flac": 60.0, "b.flac": 60.0}
    assert all(not os.path.exists(p) for p in wav_for.made)  # temp wavs deleted


def test_silent_track_keeps_name_in_mapping(wav_for):
    pipe = FakePipeline({"a.flac": [(1.0, "a1", None)]})
    res = mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for)
    assert res.mapping == {"TRACK_01": "Mike", "TRACK_02": "Sarah"}
    assert res.durations == {"a.flac": 60.0, "b.flac": 60.0}
    assert [s["text"] for s in res.segments] == ["a1"]


def test_failed_track_is_reported_and_others_continue(wav_for):
    pipe = FakePipeline(
        {"a.flac": [(1.0, "a1", None)], "b.flac": [(2.0, "b1", None)]}, fail=["b.flac"]
    )
    res = mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for)
    assert [s["text"] for s in res.segments] == ["a1"]
    assert res.failures == {"b.flac": "RuntimeError: bad audio"}
    assert "TRACK_02" not in res.mapping
    assert all(not os.path.exists(p) for p in wav_for.made)


def test_wav_duration_failure_is_contained(wav_for, monkeypatch):
    def boom(p):
        raise wave.Error("not a wav")

    import wave

    monkeypatch.setattr(mt, "wav_duration", boom)
    pipe = FakePipeline({"a.flac": [(1.0, "a1", None)]})
    res = mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for)
    assert set(res.failures) == {"a.flac", "b.flac"}
    assert res.segments == []
    assert all(not os.path.exists(p) for p in wav_for.made)


def test_shared_mic_track_gets_sub_speakers(wav_for):
    tracks = [mt.Track("a.flac", "Mike"), mt.Track("b.flac", "Sarah", shared_mic=True)]
    pipe = FakePipeline(
        {
            "a.flac": [(0.5, "a1", None)],
            "b.flac": [
                (1.0, "b1", "SPEAKER_01"),
                (3.0, "b2", "SPEAKER_00"),
                (5.0, "b3", "SPEAKER_01"),
            ],
        },
        diar_emb={"SPEAKER_00": [1.0], "SPEAKER_01": [2.0]},
    )
    res = mt.transcribe_tracks(
        pipe, tracks, wav_for=wav_for, shared_mic_count_kwargs={"num_speakers": 2}
    )
    assert [s["speaker"] for s in res.segments if s["text"].startswith("b")] == [
        "TRACK_02_SPEAKER_01",
        "TRACK_02_SPEAKER_00",
        "TRACK_02_SPEAKER_01",
    ]
    assert res.mapping == {
        "TRACK_01": "Mike",
        "TRACK_02_SPEAKER_01": "Sarah (1)",
        "TRACK_02_SPEAKER_00": "Sarah (2)",
    }
    assert pipe.calls[0] == ("a.flac", False, {})
    assert pipe.calls[1] == ("b.flac", True, {"num_speakers": 2})
    assert res.embeddings == {
        "TRACK_02_SPEAKER_00": [1.0],
        "TRACK_02_SPEAKER_01": [2.0],
    }


def test_two_diarized_tracks_stash_no_embeddings(wav_for):
    tracks = [
        mt.Track("a.flac", "Mike", shared_mic=True),
        mt.Track("b.flac", "Sarah", shared_mic=True),
    ]
    pipe = FakePipeline(
        {"a.flac": [(1.0, "a1", "SPEAKER_00")], "b.flac": [(2.0, "b1", "SPEAKER_00")]},
        diar_emb={"SPEAKER_00": [1.0]},
    )
    res = mt.transcribe_tracks(pipe, tracks, wav_for=wav_for)
    assert res.embeddings == {}


def test_same_name_on_two_tracks_kept_separate(wav_for):
    tracks = [mt.Track("a.flac", "Mike"), mt.Track("b.flac", "Mike")]
    pipe = FakePipeline({"a.flac": [(1.0, "a1", None)], "b.flac": [(2.0, "b1", None)]})
    res = mt.transcribe_tracks(pipe, tracks, wav_for=wav_for)
    assert res.mapping == {"TRACK_01": "Mike", "TRACK_02": "Mike"}
    assert [s["speaker"] for s in res.segments] == ["TRACK_01", "TRACK_02"]


def test_cancel_propagates_and_cleans_temp(wav_for):
    pipe = FakePipeline({"a.flac": [(1.0, "a1", None)], "b.flac": [(2.0, "b1", None)]})

    def progress(i, stage):
        if i == 2 and stage == "Transcribing":
            raise InterruptedError

    with pytest.raises(InterruptedError):
        mt.transcribe_tracks(pipe, _tracks(), wav_for=wav_for, progress=progress)
    assert len(wav_for.made) == 2
    assert all(not os.path.exists(p) for p in wav_for.made)


def test_progress_reports_converting_and_complete(wav_for):
    pipe = FakePipeline({"a.flac": [(1.0, "a1", None)], "b.flac": [(2.0, "b1", None)]})
    seen = []
    mt.transcribe_tracks(
        pipe, _tracks(), wav_for=wav_for, progress=lambda i, s: seen.append((i, s))
    )
    for i in (1, 2):
        stages = [s for idx, s in seen if idx == i]
        assert stages[0] == "converting"
        assert stages[-1] == "complete"
        assert "Transcribing" in stages
