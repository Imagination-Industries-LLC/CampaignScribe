"""OpenAICompatProvider: base_url handling, json mode gating, OpenRouter headers, errors."""

from __future__ import annotations

import types

import httpx
import pytest

from app.core.llm import base
from app.core.llm.openai_compat_provider import OpenAICompatProvider


def _resp(content, finish_reason="stop"):
    msg = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=msg, finish_reason=finish_reason)
    return types.SimpleNamespace(choices=[choice])


class _Completions:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def fake_openai(monkeypatch):
    import openai

    captured = {}
    state = {"outcome": _resp("hi")}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = types.SimpleNamespace(completions=_Completions(state["outcome"]))

    monkeypatch.setattr(openai, "OpenAI", _Client)

    def _set(outcome):
        state["outcome"] = outcome

    _set.captured = captured
    return _set


def _make(fake, **over):
    kw = dict(
        api_key="or-key",
        model="anthropic/claude-sonnet-4.5",
        base_url="https://openrouter.ai/api/v1",
        provider_id="openrouter",
        display_name="OpenRouter",
        supports_json_mode=True,
    )
    kw.update(over)
    return OpenAICompatProvider(kw.pop("api_key"), kw.pop("model"), kw.pop("base_url"), **kw)


def test_missing_base_url_is_missing_key_kind(fake_openai):
    with pytest.raises(base.LLMError) as ei:
        _make(fake_openai, base_url="", provider_id="custom", display_name="Custom endpoint")
    assert ei.value.kind == "missing_key"
    assert "base URL" in str(ei.value)


def test_base_url_is_normalised(fake_openai):
    p = _make(
        fake_openai,
        base_url="  http://localhost:11434/v1/  ",
        provider_id="custom",
        display_name="Custom endpoint",
        supports_json_mode=False,
    )
    assert p.base_url == "http://localhost:11434/v1"
    assert fake_openai.captured["base_url"] == "http://localhost:11434/v1"


def test_empty_key_uses_placeholder_for_local_servers(fake_openai):
    _make(fake_openai, api_key="", provider_id="custom", display_name="Custom endpoint")
    assert fake_openai.captured["api_key"] == "sk-none"


def test_openrouter_sets_attribution_headers_only_for_openrouter(fake_openai):
    _make(fake_openai)
    h = fake_openai.captured["default_headers"]
    assert h["X-Title"] == "CampaignScribe"
    assert h["HTTP-Referer"].startswith("https://github.com/")
    fake_openai.captured.clear()
    _make(fake_openai, provider_id="custom", display_name="Custom endpoint")
    assert fake_openai.captured.get("default_headers") is None


def test_timeout_and_retries(fake_openai):
    _make(fake_openai)
    assert fake_openai.captured["timeout"] == 120.0
    assert fake_openai.captured["max_retries"] == 3


def test_json_mode_sends_response_format_only_when_supported(fake_openai):
    p = _make(fake_openai)
    p.complete("hello", max_tokens=42, json_mode=True)
    call = p._client.chat.completions.calls[0]
    assert call["model"] == "anthropic/claude-sonnet-4.5"
    assert call["max_tokens"] == 42
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert call["response_format"] == {"type": "json_object"}

    q = _make(fake_openai, supports_json_mode=False)
    q.complete("hello", max_tokens=42, json_mode=True)
    assert "response_format" not in q._client.chat.completions.calls[0]


def test_none_content_is_empty_error_with_finish_reason(fake_openai):
    fake_openai(_resp(None, finish_reason="content_filter"))
    p = _make(fake_openai)
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "empty"
    assert "content_filter" in str(ei.value)


def test_auth_error_maps_to_auth(fake_openai):
    import openai

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    exc = openai.AuthenticationError("bad", response=httpx.Response(401, request=req), body=None)
    fake_openai(exc)
    p = _make(fake_openai)
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "auth"


def test_connection_error_maps_to_network(fake_openai):
    import openai

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    fake_openai(openai.APIConnectionError(request=req))
    p = _make(fake_openai)
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "network"


def test_status_error_maps_to_generic_with_code(fake_openai):
    import openai

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    exc = openai.APIStatusError("nope", response=httpx.Response(429, request=req), body=None)
    fake_openai(exc)
    p = _make(fake_openai)
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "error"
    assert "429" in str(ei.value)


def test_local_status_error_includes_server_message(fake_openai):
    import openai

    req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    exc = openai.APIStatusError(
        "x",
        response=httpx.Response(400, request=req),
        body={"error": {"message": '"nomic-embed-text:latest" does not support chat'}},
    )
    fake_openai(exc)
    p = _make(fake_openai, local_runtime="ollama")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "error"
    assert "does not support chat" in str(ei.value)
    assert "HTTP 400" in str(ei.value)


def test_timeout_s_reaches_client(fake_openai):
    _make(fake_openai, timeout_s=600.0)
    assert fake_openai.captured["timeout"] == 600.0


def test_local_runtime_network_error_asks_if_runtime_is_running(fake_openai):
    import openai

    req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    fake_openai(openai.APIConnectionError(request=req))
    p = _make(
        fake_openai,
        api_key="",
        base_url="http://localhost:11434/v1",
        provider_id="ollama",
        display_name="Ollama (local)",
        local_runtime="ollama",
    )
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "network"
    assert (
        str(ei.value) == "Could not reach Ollama (local) (APIConnectionError) — is Ollama running?"
    )


def test_cloud_network_error_unchanged(fake_openai):
    import openai

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    fake_openai(openai.APIConnectionError(request=req))
    with pytest.raises(base.LLMError) as ei:
        _make(fake_openai).complete("x", max_tokens=5)
    assert str(ei.value) == "Could not reach OpenRouter (APIConnectionError)."
