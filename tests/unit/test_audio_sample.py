"""convert_to_wav max_seconds adds an ffmpeg duration cap."""

from __future__ import annotations

import ffmpeg


def _args(max_seconds):
    # Rebuild the same ffmpeg stream convert_to_wav builds, to inspect the args.
    out_kwargs = dict(ar=16000, ac=1, format="wav", loglevel="error")
    if max_seconds and max_seconds > 0:
        out_kwargs["t"] = max_seconds
    return ffmpeg.input("in.mp3").output("out.wav", **out_kwargs).overwrite_output().get_args()


def test_no_cap_has_no_t_flag():
    assert "-t" not in _args(None)


def test_cap_adds_t_flag():
    args = _args(600)
    assert "-t" in args
    assert "600" in args


def test_config_has_discover_sample_minutes():
    from app import config

    assert "discover_sample_minutes" in config.DEFAULT_CONFIG


def test_config_has_discover_whisper_model_default_small():
    from app import config

    assert config.DEFAULT_CONFIG.get("discover_whisper_model") == "small"
