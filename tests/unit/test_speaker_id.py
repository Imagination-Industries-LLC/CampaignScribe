"""Tests for speaker_id._extract_json_object edge cases + format_segments_to_text."""

from __future__ import annotations

import pytest

from app.core import speaker_id


def test_extract_plain_json_object():
    assert speaker_id._extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_array():
    assert speaker_id._extract_json_object("[1, 2, 3]") == [1, 2, 3]


def test_extract_fenced_json():
    text = '```json\n{"a": 1, "b": 2}\n```'
    assert speaker_id._extract_json_object(text) == {"a": 1, "b": 2}


def test_extract_fenced_json_no_lang():
    text = '```\n{"a": 1}\n```'
    assert speaker_id._extract_json_object(text) == {"a": 1}


def test_extract_fenced_scalar():
    assert speaker_id._extract_json_object("```json\n42\n```") == 42


def test_extract_json_with_leading_prose():
    text = 'Here is your result:\n{"SPEAKER_00": "DM"}'
    assert speaker_id._extract_json_object(text) == {"SPEAKER_00": "DM"}


def test_extract_json_ignores_trailing_explanation():
    text = '{"a": 1}\n\nHope that helps! Let me know if you need anything else.'
    assert speaker_id._extract_json_object(text) == {"a": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        speaker_id._extract_json_object("no json here at all")


def test_format_segments_collapses_consecutive_same_speaker():
    segments = [
        {"speaker": "SPEAKER_00", "text": "Hello"},
        {"speaker": "SPEAKER_00", "text": "there"},
        {"speaker": "SPEAKER_01", "text": "Hi"},
    ]
    out = speaker_id.format_segments_to_text(segments, {})
    assert out == "SPEAKER_00: Hello there\n\nSPEAKER_01: Hi"


def test_format_segments_applies_mapping_and_skips():
    segments = [
        {"speaker": "SPEAKER_00", "text": "Narration"},
        {"speaker": "SPEAKER_02", "text": "background noise"},
        {"speaker": "SPEAKER_01", "text": "I attack"},
    ]
    out = speaker_id.format_segments_to_text(
        segments,
        {"SPEAKER_00": "DM", "SPEAKER_01": "Mike"},
        skip_speakers=["SPEAKER_02"],
    )
    assert "DM: Narration" in out
    assert "Mike: I attack" in out
    assert "background noise" not in out


def test_format_segments_skips_empty_text():
    segments = [
        {"speaker": "SPEAKER_00", "text": ""},
        {"speaker": "SPEAKER_00", "text": "real line"},
    ]
    out = speaker_id.format_segments_to_text(segments, {})
    assert out == "SPEAKER_00: real line"
