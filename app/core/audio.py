"""Audio conversion using bundled ffmpeg.exe."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core import paths


def get_ffmpeg_path() -> str:
    """Return the absolute path to the bundled ffmpeg.exe."""
    base = paths.app_home()
    candidate = base / "ffmpeg" / "ffmpeg.exe"
    if candidate.exists():
        return str(candidate)
    if paths.mode() != "dev":
        # PyInstaller --add-data sometimes flattens paths
        candidate2 = base / "ffmpeg.exe"
        if candidate2.exists():
            return str(candidate2)
    return "ffmpeg"  # fall back to PATH


def convert_to_wav(
    input_path: str, target_sr: int = 16000, max_seconds: float | None = None
) -> str:
    """Convert any audio file to mono 16kHz WAV. Returns path to a temp WAV file.

    If max_seconds is set, only the first max_seconds are converted (for fast speaker
    discovery on a sample; full transcription passes max_seconds=None).
    """
    import ffmpeg

    in_path = str(Path(input_path).resolve())
    fd, temp_wav = tempfile.mkstemp(suffix=".wav", prefix="campaignscribe_")
    os.close(fd)
    try:
        out_kwargs: dict = dict(ar=target_sr, ac=1, format="wav", loglevel="error")
        if max_seconds and max_seconds > 0:
            out_kwargs["t"] = max_seconds
        (
            ffmpeg.input(in_path)
            .output(temp_wav, **out_kwargs)
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
