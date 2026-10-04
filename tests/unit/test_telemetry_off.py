"""Third-party usage telemetry is switched off before ML libraries load."""

from __future__ import annotations

import importlib
import os

import pytest

import app.core.telemetry_off as telemetry_off

_KEYS = ("PYANNOTE_METRICS_ENABLED", "OTEL_SDK_DISABLED")


def test_transcriber_import_sets_defaults():
    import app.core.transcriber  # noqa: F401

    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "false"
    assert os.environ["OTEL_SDK_DISABLED"] == "true"


def test_apply_from_clean_env(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    importlib.reload(telemetry_off)
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "false"
    assert os.environ["OTEL_SDK_DISABLED"] == "true"


def test_explicit_user_value_is_kept(monkeypatch):
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "true")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    importlib.reload(telemetry_off)
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "true"


def test_pyannote_metrics_disabled(monkeypatch):
    pytest.importorskip("pyannote.audio")
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    importlib.reload(telemetry_off)
    from pyannote.audio.telemetry.metrics import is_metrics_enabled

    assert is_metrics_enabled() is False
