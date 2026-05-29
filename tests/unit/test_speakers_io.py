"""Tests for app.core.speakers_io: atomic save + .bak, load validation, transform."""

from __future__ import annotations

import json

import pytest

from app.core import speakers_io


def test_save_speakers_json_atomic_no_tmp(tmp_path):
    p = tmp_path / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "Curse of Strahd"})
    assert p.exists()
    assert not p.with_suffix(".json.tmp").exists()
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_save_speakers_json_creates_bak_on_overwrite(tmp_path):
    p = tmp_path / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "v1"})
    speakers_io.save_speakers_json(str(p), {"campaign": "v2"})
    bak = p.with_suffix(".json.bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8"))["campaign"] == "v1"
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "v2"


def test_save_speakers_json_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "deep" / "speakers.json"
    speakers_io.save_speakers_json(str(p), {"campaign": "x"})
    assert p.exists()


def test_load_speakers_json_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        speakers_io.load_speakers_json(str(tmp_path / "nope.json"))


def test_load_speakers_json_non_dict_raises(tmp_path):
    p = tmp_path / "speakers.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        speakers_io.load_speakers_json(str(p))


def test_load_speakers_json_fills_defaults(tmp_path):
    p = tmp_path / "speakers.json"
    p.write_text("{}", encoding="utf-8")
    data = speakers_io.load_speakers_json(str(p))
    assert data["players"] == []
    assert data["known_non_players"] == []
    assert "unknown_speaker_label" in data["fallback_policy"]


def test_profiles_to_speakers_doc_routes_players_and_non_players():
    speakers = [
        {
            "display_name": "Mike",
            "role": "Player",
            "character_name": "Wellbrix",
            "include_in_tracking": 1,
            "source_speaker_id": "SPEAKER_01",
        },
        {
            "display_name": "DM Josh",
            "role": "Non-Player",
            "include_in_tracking": 1,
            "source_speaker_id": "SPEAKER_00",
        },
        {
            "display_name": "Background",
            "role": "Player",
            "include_in_tracking": 0,
            "source_speaker_id": "SPEAKER_09",
        },
    ]
    doc = speakers_io.profiles_to_speakers_doc("Camp", "ctx", speakers)
    player_names = [p["player_name"] for p in doc["players"]]
    np_names = [n["name"] for n in doc["known_non_players"]]
    assert "Mike" in player_names
    assert "DM Josh" in np_names
    assert "Background" in np_names
    bg = next(n for n in doc["known_non_players"] if n["name"] == "Background")
    assert bg["role"] == "ignore"
