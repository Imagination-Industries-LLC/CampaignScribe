"""SessionView: ① expected count from roster, ② manual assignment + promote."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app.core import library, speakers_io
from app.data import db

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


def _campaign_with_two_players():
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc(
        "Strahd",
        "",
        [
            {"display_name": "Mike", "role": "Player", "include_in_tracking": 1},
            {"display_name": "Jo", "role": "Player", "include_in_tracking": 1},
        ],
        npcs=[],
    )
    library.add_version(slug, doc)
    return slug


def _app():
    return types.SimpleNamespace(
        notebook=None, open_session_stage=lambda sid, stage: None, open_home=lambda: None
    )


def test_confirm_seeds_expected_count_from_roster(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    assert view.expected_speaker_count() == 2  # Mike + Jo, none marked absent


def test_marking_absent_reduces_expected_count(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.mark_absent("Jo")
    assert view.expected_speaker_count() == 1


def test_add_guest_increases_expected_count(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.add_guest("Visitor")
    assert view.expected_speaker_count() == 3


def test_review_assignment_writes_session_local_mapping(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.assign_cluster("SPEAKER_00", "Mike")
    view.assign_cluster("SPEAKER_01", "__ignore__")
    view._save_session_mapping()
    rows = db.get_speakers_for_session(sid)
    by_src = {r["source_speaker_id"]: r for r in rows}
    assert by_src["SPEAKER_00"]["display_name"] == "Mike"
    assert by_src["SPEAKER_01"]["include_in_tracking"] == 0


def test_save_to_profile_adds_version(root):
    db.init_db()
    slug = _campaign_with_two_players()
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    view.assign_cluster("SPEAKER_00", "Mike")
    before = len(library.list_versions(slug))
    view._save_to_profile()
    assert len(library.list_versions(slug)) == before + 1


def test_loose_session_has_no_roster_but_constructs(root):
    db.init_db()
    sid = db.create_session("One-shot")  # null slug
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    assert view.expected_speaker_count() == 0


def test_promote_keeps_absent_roster_players(root):
    db.init_db()
    slug = _campaign_with_two_players()  # Mike + Jo
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    try:
        view.assign_cluster("SPEAKER_00", "Mike")  # only Mike showed up
        view._save_to_profile()
        doc = library.get_current_doc(slug)
        names = {p["player_name"] for p in doc["players"]}
        assert {"Mike", "Jo"} <= names  # Jo (absent) NOT dropped
    finally:
        view.destroy()


def test_promote_does_not_add_guest_to_roster(root):
    """Guest assignments are session-local (design decision D3) and must NOT be
    promoted into the campaign roster.  The UI combobox is state='readonly' so
    arbitrary new names can only enter via add_guest(); those guests should stay
    session-local and not appear in the campaign's player list after promote."""
    db.init_db()
    slug = _campaign_with_two_players()  # Mike + Jo
    sid = db.create_session("Night 1", campaign_slug=slug)
    from app.ui.session_view import GUEST_CHOICE, SessionView

    view = SessionView(root, _app(), sid)
    root.update_idletasks()
    try:
        view.assign_cluster("SPEAKER_00", "Mike")
        view.assign_cluster("SPEAKER_01", GUEST_CHOICE)  # one-night-only guest
        view._save_to_profile()
        doc = library.get_current_doc(slug)
        names = {p["player_name"] for p in doc["players"]}
        # Mike and Jo must survive; the guest cluster must NOT create a new player
        assert {"Mike", "Jo"} <= names
        assert not any(n == "" or n == GUEST_CHOICE for n in names)
        assert len(names) == 2  # no extra entry from the guest cluster
    finally:
        view.destroy()


def test_review_prefills_names_from_persisted_track_rows(root):
    from app.data import db
    from app.ui.session_view import SessionView

    db.init_db()
    sid = db.create_session("Tracks")
    for cid, name in (("TRACK_01", "Mike"), ("TRACK_02", "Sarah")):
        db.add_speaker_profile(
            sid, {"source_speaker_id": cid, "display_name": name, "include_in_tracking": 1}
        )
    mixed = db.create_session("Mixed")
    for cid in ("SPEAKER_00", "SPEAKER_01"):
        db.add_speaker_profile(
            mixed, {"source_speaker_id": cid, "display_name": "", "include_in_tracking": 1}
        )
    app = types.SimpleNamespace(
        notebook=None, open_session_stage=lambda *a: None, open_home=lambda: None
    )
    view = SessionView(root, app, sid)
    root.update_idletasks()
    assert {c: v.get() for c, v in view._review_vars.items()} == {
        "TRACK_01": "Mike",
        "TRACK_02": "Sarah",
    }
    view2 = SessionView(root, app, mixed)
    root.update_idletasks()
    assert {v.get() for v in view2._review_vars.values()} == {""}
