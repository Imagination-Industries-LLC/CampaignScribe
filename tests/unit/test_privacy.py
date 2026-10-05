"""Tests for app.core.privacy: PRIVACY.md loader, fallback, and constants."""

from __future__ import annotations

from app.core import privacy


def test_load_privacy_text_reads_repo_privacy_md():
    text = privacy.load_privacy_text()
    assert "Stays on your computer" in text
    assert "Anthropic Claude API" in text
    assert "does NOT" in text or "What CampaignScribe does NOT do" in text


def test_load_privacy_text_matches_repo_file():
    # The dialog's single source of truth IS PRIVACY.md.
    from pathlib import Path

    repo_md = Path(privacy.__file__).resolve().parents[2] / "PRIVACY.md"
    assert repo_md.exists()
    assert privacy.load_privacy_text() == repo_md.read_text(encoding="utf-8")


def test_load_privacy_text_falls_back_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(privacy, "_privacy_md_path", lambda: tmp_path / "nope.md")
    assert privacy.load_privacy_text() == privacy._FALLBACK


def test_load_privacy_text_falls_back_on_decode_error(monkeypatch, tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\x00invalid utf-8 \xc3\x28")
    monkeypatch.setattr(privacy, "_privacy_md_path", lambda: bad)
    assert privacy.load_privacy_text() == privacy._FALLBACK


def test_urls_are_https():
    assert privacy.ANTHROPIC_PRIVACY_URL.startswith("https://")
    assert privacy.PRIVACY_MD_URL.startswith("https://")


def test_inline_note_functions_name_vendor_and_help():
    for fn in (privacy.note_samples, privacy.note_transcript):
        note = fn("Google (Gemini)")
        assert "Google (Gemini)" in note
        assert "Privacy & Data" in note
    assert privacy.NOTE_SAMPLES == privacy.note_samples("Anthropic (Claude)")
    assert privacy.NOTE_TRANSCRIPT == privacy.note_transcript("Anthropic (Claude)")


def test_all_provider_privacy_urls_are_https():
    for url in (
        privacy.ANTHROPIC_PRIVACY_URL,
        privacy.GEMINI_PRIVACY_URL,
        privacy.OPENROUTER_PRIVACY_URL,
    ):
        assert url.startswith("https://")


def test_privacy_has_discord_recording_section():
    text = privacy.load_privacy_text()
    assert "## Discord recording" in text
    for phrase in ("Discord's servers", "Windows Credential Manager", "recordings folder"):
        assert phrase in text
    assert "shown in Settings" not in text
    assert "recordings_folder" in text
