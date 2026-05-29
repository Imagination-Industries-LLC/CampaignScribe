"""Audio conversion using bundled ffmpeg.exe."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def get_ffmpeg_path() -> str:
    """Return the absolute path to the bundled ffmpeg.exe."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        candidate = base / "ffmpeg" / "ffmpeg.exe"
        if candidate.exists():
            return str(candidate)
        # PyInstaller --add-data sometimes flattens paths
        candidate2 = base / "ffmpeg.exe"
        if candidate2.exists():
            return str(candidate2)
    here = Path(__file__).resolve().parent.parent.parent
    candidate = here / "ffmpeg" / "ffmpeg.exe"
    if candidate.exists():
        return str(candidate)
    return "ffmpeg"  # fall back to PATH


def convert_to_wav(input_path: str, target_sr: int = 16000) -> str:
    """Convert any audio file to mono 16kHz WAV. Returns path to a temp WAV file."""
    import ffmpeg

    in_path = str(Path(input_path).resolve())
    fd, temp_wav = tempfile.mkstemp(suffix=".wav", prefix="campaignscribe_")
    os.close(fd)
    try:
        (
            ffmpeg
            .input(in_path)
            .output(temp_wav, ar=target_sr, ac=1, format="wav", loglevel="error")
            .overwrite_output()
            .run(quiet=True, cmd=get_ffmpeg_path())
        )
    except ffmpeg.Error as e:
        try:
            os.remove(temp_wav)
        except OSError:
            pass
        msg = e.stderr.decode("utf-8", errors="replace") if getattr(e, "stderr", None) else str(e)
        raise RuntimeError(f"ffmpeg conversion failed: {msg}") from e
    return temp_wav
