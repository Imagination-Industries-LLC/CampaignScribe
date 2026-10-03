"""Tests for summarizer helpers + consolidate_summaries (mocked provider) + docx export."""

from __future__ import annotations

from app.core import summarizer


def test_safe_filename_strips_invalid_and_spaces():
    assert summarizer.safe_filename("Session 1: The Crypt!") == "Session_1_The_Crypt"


def test_safe_filename_empty_falls_back():
    assert summarizer.safe_filename("***") == "Session_Summary"


def test_parse_session_name_found():
    text = "SESSION NAME: The Sunless Citadel\n\nThings happened."
    assert summarizer.parse_session_name_from_text(text) == "The Sunless Citadel"


def test_parse_session_name_absent():
    assert summarizer.parse_session_name_from_text("no header here") is None


def test_consolidate_summaries_parses_name_and_body(fake_provider):
    provider = fake_provider(["SESSION NAME: Into the Mist\n\n## Recap\nThe party fled."])
    result = summarizer.consolidate_summaries(["part 1 summary"], {"campaign": "Strahd"}, provider)
    assert result["session_name"] == "Into the Mist"
    assert "The party fled." in result["body"]
    assert result["raw"].startswith("SESSION NAME:")
    assert not result["body"].startswith("SESSION NAME:")
    assert provider.calls[0]["json_mode"] is False
    assert provider.calls[0]["max_tokens"] == 4000


def test_consolidate_summaries_defaults_name_when_missing(fake_provider):
    provider = fake_provider(["No name header, just prose."])
    result = summarizer.consolidate_summaries(["p1"], {}, provider)
    assert result["session_name"] == "Session Summary"


def test_write_docx_creates_file(tmp_path):
    out = tmp_path / "out" / "summary.docx"
    summarizer.write_docx(
        str(out),
        session_name="Test Session",
        consolidated_body="## Recap\n- point one\n- point two\n\nKEY EVENTS\nStuff.",
        part_summaries=["Part one text"],
        campaign_name="Strahd",
    )
    assert out.exists()
    assert out.stat().st_size > 0
