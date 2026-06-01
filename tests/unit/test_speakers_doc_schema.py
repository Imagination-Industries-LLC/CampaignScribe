"""Doc-schema extension: per-speaker ignore flag + campaign-level npcs list."""

from __future__ import annotations

import json

from app.core import library, speakers_io


def test_empty_doc_has_npcs_and_ignore_defaults():
    doc = speakers_io.empty_speakers_doc("Strahd")
    assert doc["npcs"] == []
    assert doc["players"] == []


def test_profiles_to_doc_marks_ignored_speaker():
    speakers = [
        {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
        {"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0},
    ]
    doc = speakers_io.profiles_to_speakers_doc("Strahd", "", speakers, npcs=[])
    assert any(n.get("ignore") is True for n in doc["known_non_players"])
    assert all(p["player_name"] != "TV" for p in doc["players"])


def test_profiles_to_doc_round_trips_npcs():
    npcs = [{"name": "Strahd", "notes": "the vampire"}]
    doc = speakers_io.profiles_to_speakers_doc("Strahd", "ctx", [], npcs=npcs)
    assert doc["npcs"] == npcs


def test_old_doc_without_npcs_still_loads(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"campaign": "Old", "players": []}), encoding="utf-8")
    doc = speakers_io.load_speakers_json(str(p))
    assert doc["npcs"] == []  # default-filled
    assert doc["campaign"] == "Old"


def test_npcs_and_ignore_round_trip_through_library(tmp_path):
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd",
        "",
        [{"display_name": "TV", "role": "Non-Player", "include_in_tracking": 0}],
        npcs=[{"name": "Strahd", "notes": "vampire"}],
    )
    library.add_version(slug, doc)
    got = library.get_current_doc(slug)
    assert got["npcs"] == [{"name": "Strahd", "notes": "vampire"}]
    assert any(n.get("ignore") is True for n in got["known_non_players"])
