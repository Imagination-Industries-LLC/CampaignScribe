"""Unit test: TranscribeTab._persist_detected_speakers records diarized clusters."""

from __future__ import annotations

import types


def test_persist_detected_speakers_records_clusters():
    from app.data import db

    db.init_db()
    sid = db.create_session("S")
    # call the helper without constructing the Tk tab: bind it to a dummy
    from app.ui import transcribe_tab

    segs = [{"speaker": "SPEAKER_00"}, {"speaker": "SPEAKER_00"}, {"speaker": "SPEAKER_01"}]
    transcribe_tab.TranscribeTab._persist_detected_speakers(types.SimpleNamespace(), sid, segs)
    assert db.get_session(sid)["num_speakers_detected"] == 2
    ids = {r["source_speaker_id"] for r in db.get_speakers_for_session(sid)}
    assert ids == {"SPEAKER_00", "SPEAKER_01"}
