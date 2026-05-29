"""Tests for app.data.db: schema/version, column allowlist, CRUD, cascade, JSON fields."""

from __future__ import annotations

import pytest

from app.data import db


def test_init_db_sets_user_version_to_baseline():
    db.init_db()
    with db.get_conn() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
    assert version == db.SCHEMA_BASELINE


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()
    with db.get_conn() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_BASELINE


def test_get_conn_enables_foreign_keys():
    db.init_db()
    with db.get_conn() as c:
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_update_session_rejects_unknown_column():
    db.init_db()
    sid = db.create_session("Test")
    with pytest.raises(ValueError):
        db.update_session(sid, status="done; DROP TABLE sessions")


def test_update_session_accepts_allowlisted_column():
    db.init_db()
    sid = db.create_session("Test")
    db.update_session(sid, status="complete")
    assert db.get_session(sid)["status"] == "complete"


def test_update_speaker_profile_rejects_unknown_column():
    db.init_db()
    sid = db.create_session("Test")
    pid = db.add_speaker_profile(sid, {"display_name": "Mike"})
    with pytest.raises(ValueError):
        db.update_speaker_profile(pid, bogus_col="x")


def test_speaker_profile_json_fields_roundtrip():
    db.init_db()
    sid = db.create_session("Test")
    pid = db.add_speaker_profile(
        sid,
        {
            "display_name": "Mike",
            "speech_patterns": ["says 'huzzah'"],
            "sample_quotes": ["I attack!"],
        },
    )
    rows = db.get_speakers_for_session(sid)
    row = next(r for r in rows if r["id"] == pid)
    assert row["speech_patterns"] == ["says 'huzzah'"]
    assert row["sample_quotes"] == ["I attack!"]


def test_delete_session_cascades_to_profiles():
    db.init_db()
    sid = db.create_session("Test")
    db.add_speaker_profile(sid, {"display_name": "Mike"})
    db.delete_session(sid)
    assert db.get_speakers_for_session(sid) == []


def test_list_sessions_search_filters():
    db.init_db()
    db.create_session("Strahd Recap", campaign_name="Curse of Strahd")
    db.create_session("Other", campaign_name="Different")
    results = db.list_sessions(search="Strahd")
    assert any("Strahd" in r["display_name"] for r in results)
    assert all(
        "Strahd" in r["display_name"] or "Strahd" in (r["campaign_name"] or "") for r in results
    )
