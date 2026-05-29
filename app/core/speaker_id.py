"""Claude API helpers for speaker discovery, identification, and refinement.

Adapted from the reference format_transcript.py.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core import transcriber as _transcriber

CLAUDE_MODEL = "claude-sonnet-4-20250514"


def _client(api_key: str):
    from app.core.claude_api import make_client

    return make_client(api_key)


def _extract_json_object(text: str) -> Any:
    """Pull the first COMPLETE JSON object/array out of a Claude response,
    tolerating markdown fences and surrounding prose.

    Scans from each candidate opening brace with json.JSONDecoder.raw_decode,
    so trailing explanation text (or a second JSON-ish block) can't corrupt the
    parse the way a greedy ``\\{.*\\}`` regex would."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    # Fast path: the whole response is valid JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Scan for the first '{' or '[' that begins a complete, valid JSON value.
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _end = decoder.raw_decode(text, i)
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("Could not parse JSON from Claude response.")


def _send(api_key: str, prompt: str, max_tokens: int = 4000) -> str:
    client = _client(api_key)
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# ---------- Tab 1: speaker discovery ----------

DISCOVERY_PROMPT_TEMPLATE = """You are analyzing transcript samples from a tabletop RPG (D&D) session to build initial speaker profiles.

Your task: identify distinct speakers, infer whether each is the Dungeon Master or a player, and extract specific speech fingerprints useful for future automated speaker identification.

LOOK FOR:
- DM signs: narrates scenes, voices NPCs in third person ("She says...", "He goes..."), calls for dice rolls ("Roll me a...", "Give me a perception check"), assigns loot, describes combat outcomes
- Player signs: declares character actions ("I attack the goblin"), asks what they see, asks rules questions, reacts to DM narration, speaks in character
- Speech tics, recurring phrases, vocabulary
- Any names mentioned (may reveal character or player names)
- Topics unique to this person (rules focus, jokes, real-life tangents, character backstory)

RULES:
- Only create profiles for speakers with sufficient sample data (at least 5 lines)
- Do not invent details not in the samples
- Mark confidence: high / medium / low
- One speaker is almost certainly the DM

Return ONLY valid JSON, no markdown fences, matching this exact schema:

{{
  "num_speakers_detected": 5,
  "onboarding_notes": "Brief summary of what was inferred and what needs DM review",
  "profiles": [
    {{
      "source_speaker_id": "SPEAKER_00",
      "inferred_role": "DM",
      "confidence": "high",
      "suggested_display_name": "DM",
      "notes": "Narrates all scenes, voices NPCs, calls for dice rolls",
      "speech_patterns": ["Uses 'Roll me a...' before checks", "Introduces NPCs in third person"],
      "sample_quotes": ["Roll me a perception check.", "She looks you over and sighs."]
    }}
  ]
}}

SPEAKER SAMPLES:
{samples}
"""


def discover_speakers(segments: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    samples = _transcriber.collect_speaker_samples(segments, max_lines=30)
    samples_text = "\n\n".join(
        f"{sid}:\n" + "\n".join(f"  - {line}" for line in lines)
        for sid, lines in sorted(samples.items())
    )
    prompt = DISCOVERY_PROMPT_TEMPLATE.format(samples=samples_text)
    raw = _send(api_key, prompt, max_tokens=4000)
    parsed = _extract_json_object(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Discovery response was not a JSON object.")
    parsed.setdefault("num_speakers_detected", len(samples))
    parsed.setdefault("onboarding_notes", "")
    parsed.setdefault("profiles", [])
    return parsed


# ---------- Tab 3: speaker identification (mapping SPEAKER_XX -> player names) ----------

ID_PROMPT_TEMPLATE = """You are helping identify speakers in a D&D session transcript.

CAMPAIGN CONTEXT:
{campaign_json}

SPEAKER SAMPLES:
Below are sample lines spoken by each automatically-detected speaker ID.
Use the campaign context, player roles, character names, speech patterns, and
D&D terminology to match each speaker ID to the most likely real person.

{samples}

Return ONLY a JSON object mapping each speaker ID to a player name, like this:
{{"SPEAKER_00": "Josh (DM)", "SPEAKER_01": "Mike (Wellbrix)"}}

Use the player_name field from the campaign context for the values; you may include
the character name in parentheses for clarity. If a speaker matches a known_non_players
entry, use that label (e.g. "Mike's Wife (non-player)"). If you cannot confidently
identify a speaker, fall back to the "fallback_policy" unknown_speaker_label or use
the original speaker id.
Return only the JSON object, no explanation, no markdown fences."""


def identify_speakers(
    segments: list[dict[str, Any]],
    speakers_reference: dict[str, Any],
    api_key: str,
) -> dict[str, str]:
    samples = _transcriber.collect_speaker_samples(segments, max_lines=15)
    if not samples:
        return {}
    samples_text = "\n\n".join(
        f"{sid}:\n" + "\n".join(f"  - {line}" for line in lines)
        for sid, lines in sorted(samples.items())
    )
    prompt = ID_PROMPT_TEMPLATE.format(
        campaign_json=json.dumps(speakers_reference, indent=2),
        samples=samples_text,
    )
    raw = _send(api_key, prompt, max_tokens=1000)
    try:
        parsed = _extract_json_object(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        pass
    return {sid: sid for sid in samples}


def format_segments_to_text(
    segments: list[dict[str, Any]],
    speaker_mapping: dict[str, str],
    skip_speakers: list[str] = None,
) -> str:
    """Collapse consecutive segments by the same speaker, optionally skipping ignored ones."""
    skip_speakers = set(skip_speakers or [])
    lines: list[str] = []
    current_speaker: str = ""
    current_text: list[str] = []

    def flush():
        if current_text:
            lines.append(f"{current_speaker}: {' '.join(current_text)}")

    for seg in segments:
        raw_id = seg.get("speaker") or "UNKNOWN"
        if raw_id in skip_speakers:
            continue
        speaker = speaker_mapping.get(raw_id, raw_id)
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if speaker != current_speaker:
            flush()
            current_speaker = speaker
            current_text = [text]
        else:
            current_text.append(text)
    flush()
    return "\n\n".join(lines)


# ---------- Tab 3 / Tab 5 follow-up: speaker refinement ----------

REFINEMENT_PROMPT_TEMPLATE = """You are analyzing new audio transcript samples to improve an existing set of D&D speaker profiles.

EXISTING SPEAKERS.JSON:
{existing}

NEW AUDIO TRANSCRIPT SAMPLES:
{samples}

YOUR TASKS:

1. MATCH new speaker IDs to existing profiles where confident
2. For matched speakers: suggest NEW speech patterns or sample quotes not already in their profile
   - Only suggest additions, never suggest removing existing patterns
   - Only suggest if genuinely new and distinct from what's already there
3. IDENTIFY unmatched speaker IDs that don't match any existing profile
   - For each: provide inferred role, confidence, notes, sample quotes
4. SUGGEST speakers that appear to be non-players or background voices that should be ignored
   - These should be added to known_non_players with an ignore flag

Return ONLY valid JSON, no markdown fences:

{{
  "improvements": [
    {{
      "existing_player_name": "Josh",
      "source_speaker_id": "SPEAKER_00",
      "new_speech_patterns": ["New pattern identified"],
      "new_sample_quotes": ["New quote"],
      "confidence": "high"
    }}
  ],
  "new_speakers": [
    {{
      "source_speaker_id": "SPEAKER_05",
      "inferred_role": "Player",
      "confidence": "medium",
      "suggested_display_name": "New Player",
      "notes": "Speaks sparingly, asks rules questions",
      "speech_patterns": ["Asks rules clarification questions"],
      "sample_quotes": ["Wait, can I use my bonus action for that?"]
    }}
  ],
  "suggested_ignores": [
    {{
      "source_speaker_id": "SPEAKER_06",
      "reason": "Appears to be a background voice or non-participant",
      "sample_quote": "Brief unintelligible background line"
    }}
  ]
}}
"""


def refine_speakers(
    segments: list[dict[str, Any]],
    speakers_reference: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    samples = _transcriber.collect_speaker_samples(segments, max_lines=20)
    samples_text = "\n\n".join(
        f"{sid}:\n" + "\n".join(f"  - {line}" for line in lines)
        for sid, lines in sorted(samples.items())
    )
    prompt = REFINEMENT_PROMPT_TEMPLATE.format(
        existing=json.dumps(speakers_reference, indent=2),
        samples=samples_text,
    )
    raw = _send(api_key, prompt, max_tokens=4000)
    try:
        parsed = _extract_json_object(raw)
        if isinstance(parsed, dict):
            parsed.setdefault("improvements", [])
            parsed.setdefault("new_speakers", [])
            parsed.setdefault("suggested_ignores", [])
            return parsed
    except Exception:
        pass
    return {"improvements": [], "new_speakers": [], "suggested_ignores": []}
