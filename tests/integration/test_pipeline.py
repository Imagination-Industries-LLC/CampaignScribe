"""Integration: identify -> format -> summarize -> consolidate with mocked LLM + diarization."""
from __future__ import annotations

from app.core import speaker_id, summarizer

SEGMENTS = [
    {"speaker": "SPEAKER_00", "text": "Roll me a perception check."},
    {"speaker": "SPEAKER_01", "text": "I rolled a 17."},
    {"speaker": "SPEAKER_00", "text": "You spot a hidden door."},
]

SPEAKERS_REF = {
    "campaign": "Curse of Strahd",
    "context": "Gothic horror",
    "players": [{"player_name": "Mike", "character_name": "Wellbrix"}],
}


def test_identify_then_format(monkeypatch, fake_claude):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"], "SPEAKER_01": ["b"]},
    )
    fake_claude(['{"SPEAKER_00": "Josh (DM)", "SPEAKER_01": "Mike (Wellbrix)"}'])

    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, api_key="sk-x")
    assert mapping["SPEAKER_00"] == "Josh (DM)"

    transcript = speaker_id.format_segments_to_text(SEGMENTS, mapping)
    assert "Josh (DM): Roll me a perception check." in transcript
    assert "Mike (Wellbrix): I rolled a 17." in transcript


def test_identify_falls_back_on_bad_llm_json(monkeypatch, fake_claude):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"]},
    )
    fake_claude(["the model rambled and returned no json"])
    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, api_key="sk-x")
    assert mapping == {"SPEAKER_00": "SPEAKER_00"}


def test_summarize_then_consolidate(fake_claude):
    client = fake_claude([
        "## Part 1\nThe party entered the crypt.",
        "SESSION NAME: The Crypt\n\n## Recap\nAll survived.",
    ])
    transcript = "DM: You enter a crypt.\n\nMike: I draw my sword."
    part = summarizer.summarize_part(transcript, SPEAKERS_REF, "Summarize this.", "sk-x", 1)
    assert "crypt" in part.lower()

    result = summarizer.consolidate_summaries([part], SPEAKERS_REF, api_key="sk-x")
    assert result["session_name"] == "The Crypt"
    assert len(client.calls) == 2
