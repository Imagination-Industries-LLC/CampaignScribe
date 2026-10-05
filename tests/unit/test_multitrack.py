"""Pure helpers for one-file-per-speaker transcription."""

from __future__ import annotations

import wave

import pytest

from app.core import multitrack as mt


@pytest.mark.parametrize(
    "path, expected",
    [
        ("rec/1-mike_1234.flac", "mike"),  # Craig
        ("rec/12-Sarah Q_0.ogg", "Sarah Q"),  # Craig, space in name
        ("rec/Mike_1083839469700001892.wav", "Mike"),  # CampaignScribe recorder
        ("rec/Sarah.m4a", "Sarah"),  # plain
        ("rec/dungeon_master.wav", "dungeon master"),  # underscores -> spaces
        ("rec/take_2.wav", "take 2"),  # short trailing digits kept
        ("rec/  Bob  .wav", "Bob"),
    ],
)
def test_name_from_filename(path, expected):
    assert mt.name_from_filename(path) == expected


def test_track_label_is_one_based_and_padded():
    assert mt.track_label(1) == "TRACK_01"
    assert mt.track_label(12) == "TRACK_12"


def test_merge_orders_by_start_then_track_order():
    a = [
        {"start": 1.0, "end": 2.0, "text": "a1", "speaker": "TRACK_01"},
        {"start": 5.0, "end": 6.0, "text": "a2", "speaker": "TRACK_01"},
    ]
    b = [
        {"start": 1.0, "end": 1.5, "text": "b1", "speaker": "TRACK_02"},
        {"start": 3.0, "end": 4.0, "text": "b2", "speaker": "TRACK_02"},
    ]
    merged = mt.merge_segments([a, [], b])
    assert [s["text"] for s in merged] == ["a1", "b1", "b2", "a2"]


def test_merge_handles_missing_start_as_zero():
    merged = mt.merge_segments([[{"start": None, "end": 1, "text": "x", "speaker": "TRACK_01"}]])
    assert merged[0]["text"] == "x"


def test_duration_mismatch():
    assert mt.duration_mismatch({"a.wav": 3600.0, "b.wav": 3601.5}) == ""
    msg = mt.duration_mismatch({"a.wav": 3600.0, "b.wav": 3500.0})
    assert "b.wav" in msg and "a.wav" in msg
    assert mt.duration_mismatch({}) == ""


def test_wav_duration(tmp_path):
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * 3)
    assert mt.wav_duration(str(p)) == pytest.approx(3.0)
