"""speaker_id routes every LLM call through provider.complete with json_mode=True."""

from __future__ import annotations

from app.core import speaker_id

SEGMENTS = [
    {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Roll initiative."},
    {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01", "text": "Natural twenty!"},
]


def test_discover_uses_json_mode_and_fills_defaults(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=30: {"SPEAKER_00": ["a"], "SPEAKER_01": ["b"]},
    )
    provider = fake_provider(['{"profiles": [{"source_speaker_id": "SPEAKER_00"}]}'])
    out = speaker_id.discover_speakers(SEGMENTS, provider)
    assert out["profiles"][0]["source_speaker_id"] == "SPEAKER_00"
    assert out["num_speakers_detected"] == 2
    call = provider.calls[0]
    assert call["json_mode"] is True
    assert call["max_tokens"] == 4000


def test_identify_requests_1000_tokens_json(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"]},
    )
    provider = fake_provider(['{"SPEAKER_00": "DM"}'])
    assert speaker_id.identify_speakers(SEGMENTS, {"players": []}, provider) == {"SPEAKER_00": "DM"}
    assert provider.calls[0] == {
        "prompt": provider.calls[0]["prompt"],
        "max_tokens": 1000,
        "json_mode": True,
    }


def test_refine_falls_back_to_empty_lists_on_garbage(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=20: {"SPEAKER_00": ["a"]},
    )
    provider = fake_provider(["not json at all"])
    out = speaker_id.refine_speakers(SEGMENTS, {"players": []}, provider)
    assert out == {"improvements": [], "new_speakers": [], "suggested_ignores": []}
    assert provider.calls[0]["json_mode"] is True
