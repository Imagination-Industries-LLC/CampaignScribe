"""Tests for app.core.claude_api.make_client: empty-key guard + timeout/retry config."""

from __future__ import annotations

import pytest

from app.core import claude_api


def test_make_client_raises_on_empty_key():
    with pytest.raises(RuntimeError):
        claude_api.make_client("")


def test_make_client_configures_timeout_and_retries(monkeypatch):
    captured = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)

    client = claude_api.make_client("sk-test")
    assert isinstance(client, _FakeAnthropic)
    assert captured["api_key"] == "sk-test"
    assert captured["max_retries"] == claude_api._MAX_RETRIES
    assert captured["timeout"].connect == claude_api._TIMEOUT_CONNECT
    assert captured["timeout"].read == claude_api._TIMEOUT_TOTAL
