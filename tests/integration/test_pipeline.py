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


def test_identify_then_format(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"], "SPEAKER_01": ["b"]},
    )
    provider = fake_provider(['{"SPEAKER_00": "Josh (DM)", "SPEAKER_01": "Mike (Wellbrix)"}'])

    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, provider)
    assert provider.calls[0]["json_mode"] is True
    assert mapping["SPEAKER_00"] == "Josh (DM)"

    transcript = speaker_id.format_segments_to_text(SEGMENTS, mapping)
    assert "Josh (DM): Roll me a perception check." in transcript
    assert "Mike (Wellbrix): I rolled a 17." in transcript


def test_identify_falls_back_on_bad_llm_json(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"]},
    )
    provider = fake_provider(["the model rambled and returned no json"])
    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, provider)
    assert mapping == {"SPEAKER_00": "SPEAKER_00"}


def test_summarize_then_consolidate(fake_provider):
    provider = fake_provider(
        [
            "## Part 1\nThe party entered the crypt.",
            "SESSION NAME: The Crypt\n\n## Recap\nAll survived.",
        ]
    )
    transcript = "DM: You enter a crypt.\n\nMike: I draw my sword."
    part = summarizer.summarize_part(transcript, SPEAKERS_REF, "Summarize this.", provider, 1)
    assert "crypt" in part.lower()

    result = summarizer.consolidate_summaries([part], SPEAKERS_REF, provider)
    assert result["session_name"] == "The Crypt"
    assert len(provider.calls) == 2, (
        f"Expected 2 LLM calls (summarize_part + consolidate_summaries), got {len(provider.calls)}"
    )
    assert all(c["json_mode"] is False for c in provider.calls)
