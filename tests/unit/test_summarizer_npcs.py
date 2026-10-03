"""known_npcs threads campaign NPCs into the summary prompt sent to the LLM."""

from __future__ import annotations

from app.core import summarizer


def _prompt_of(provider) -> str:
    assert provider.calls, "provider.complete was never called"
    return provider.calls[0]["prompt"]


def test_summarize_part_includes_known_npcs(fake_provider):
    provider = fake_provider(["a part summary"])
    summarizer.summarize_part(
        "TRANSCRIPT TEXT",
        {"campaign": "Strahd", "context": "", "players": []},
        "Summarize this session.",
        provider,
        part_number=1,
        known_npcs=["Strahd", "Ireena"],
    )
    prompt = _prompt_of(provider)
    assert "Known NPCs in this campaign:" in prompt
    assert "Strahd" in prompt
    assert "Ireena" in prompt


def test_summarize_part_without_npcs_is_unchanged(fake_provider):
    prov_a = fake_provider(["s"])
    summarizer.summarize_part(
        "T", {"campaign": "C", "context": "", "players": []}, "P", prov_a, part_number=1
    )
    base_prompt = _prompt_of(prov_a)
    assert "Known NPCs in this campaign:" not in base_prompt

    prov_b = fake_provider(["s"])
    summarizer.summarize_part(
        "T",
        {"campaign": "C", "context": "", "players": []},
        "P",
        prov_b,
        part_number=1,
        known_npcs=[],
    )
    assert _prompt_of(prov_b) == base_prompt  # empty list == None == unchanged


def test_consolidate_includes_known_npcs(fake_provider):
    provider = fake_provider(["SESSION NAME: X\n\nbody"])
    summarizer.consolidate_summaries(
        ["part 1 summary"],
        {"campaign": "Strahd", "context": ""},
        provider,
        known_npcs=["Strahd"],
    )
    assert "Strahd" in _prompt_of(provider)
    assert "Known NPCs in this campaign:" in _prompt_of(provider)
