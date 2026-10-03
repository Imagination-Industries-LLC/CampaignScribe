"""AnthropicProvider: client policy, text extraction, error mapping (fake SDK client)."""

from __future__ import annotations

import httpx
import pytest

from app.core.llm import base
from app.core.llm.anthropic_provider import AnthropicProvider


class _Block:
    def __init__(self, text, type_="text"):
        self.text = text
        self.type = type_


class _Resp:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content = blocks
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patch anthropic.Anthropic with a capturing fake; returns a setter for the outcome."""
    import anthropic

    captured = {}
    state = {"outcome": _Resp([_Block("hi")])}

    class _Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.messages = _Messages(state["outcome"])

    monkeypatch.setattr(anthropic, "Anthropic", _Fake)

    def _set(outcome):
        state["outcome"] = outcome

    _set.captured = captured
    return _set


def test_empty_key_raises_missing_key():
    with pytest.raises(base.LLMError) as ei:
        AnthropicProvider("", "claude-sonnet-5-5")
    assert ei.value.kind == "missing_key"
    assert "Claude" in str(ei.value)


def test_client_uses_anthropic_timeout_and_retries(fake_anthropic):
    import anthropic

    AnthropicProvider("sk-test", "claude-sonnet-5-5")
    cap = fake_anthropic.captured
    assert cap["api_key"] == "sk-test"
    assert cap["max_retries"] == 3
    assert isinstance(cap["timeout"], anthropic.Timeout)
    assert cap["timeout"].connect == 10.0
    assert cap["timeout"].read == 120.0


def test_complete_sends_model_and_prompt_and_joins_text_blocks(fake_anthropic):
    fake_anthropic(_Resp([_Block("part one "), _Block("ignored", "tool_use"), _Block("part two")]))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    out = p.complete("hello", max_tokens=55, json_mode=True)
    assert out == "part one part two"
    call = p._client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] == 55
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert "response_format" not in call  # prompt-level JSON only


def test_refusal_or_blank_response_is_empty_error(fake_anthropic):
    fake_anthropic(_Resp([], stop_reason="refusal"))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "empty"
    assert "refusal" in str(ei.value)


def test_auth_error_maps_to_auth_kind(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError(
        "bad key", response=httpx.Response(401, request=req), body=None
    )
    fake_anthropic(exc)
    p = AnthropicProvider("sk-bad", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "auth"


def test_connection_error_maps_to_network_kind(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_anthropic(anthropic.APIConnectionError(request=req))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "network"


def test_other_status_error_maps_to_generic_with_code(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIStatusError("boom", response=httpx.Response(529, request=req), body=None)
    fake_anthropic(exc)
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "error"
    assert "529" in str(ei.value)
