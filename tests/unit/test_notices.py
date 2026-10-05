from __future__ import annotations

from app.core import notices


def test_loads_bundled_file():
    text = notices.load_notices_text()
    for needle in (
        "pyannote",
        "pyannote/segmentation",
        "Hervé Bredin",
        "CC-BY-4.0",
        "WeSpeaker",
        "VoxCeleb",
        "VBx",
        "Whisper",
        "WhisperX",
        "faster-whisper",
        "CTranslate2",
        "Node.js",
        "@discordjs/voice",
    ):
        assert needle in text, needle


def test_notices_fallback_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(notices, "_notices_path", lambda: tmp_path / "nope.md")
    assert notices.load_notices_text() == notices._FALLBACK
    assert "THIRD-PARTY-NOTICES" in notices._FALLBACK
