"""GeminiProvider: config mapping (json mode, relaxed safety), empty/blocked handling, errors."""

from __future__ import annotations

import types

import httpx
import pytest

from app.core.llm import base
from app.core.llm.gemini_provider import GeminiProvider


class _Resp:
    def __init__(self, text=None, candidates=None, prompt_feedback=None, text_raises=False):
        self._text = text
        self._text_raises = text_raises
        self.candidates = candidates if candidates is not None else []
        self.prompt_feedback = prompt_feedback

    @property
    def text(self):
        if self._text_raises:
            raise ValueError("no parts")
        return self._text


class _Models:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def fake_genai(monkeypatch):
    from google import genai

    captured = {}
    state = {"outcome": _Resp(text="hi")}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = _Models(state["outcome"])

    monkeypatch.setattr(genai, "Client", _Client)

    def _set(outcome):
        state["outcome"] = outcome

    _set.captured = captured
    return _set


def test_empty_key_raises_missing_key():
    with pytest.raises(base.LLMError) as ei:
        GeminiProvider("", "gemini-2.5-flash")
    assert ei.value.kind == "missing_key"
    assert "Google Gemini" in str(ei.value)


def test_client_gets_key_and_timeout(fake_genai):
    GeminiProvider("g-key", "gemini-2.5-flash")
    assert fake_genai.captured["api_key"] == "g-key"
    assert fake_genai.captured["http_options"].timeout == 120_000
    assert fake_genai.captured["http_options"].retry_options.attempts == 4


def test_flash_model_disables_thinking(fake_genai):
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    assert p._config(64, False).thinking_config.thinking_budget == 0


def test_non_flash_model_leaves_thinking_default(fake_genai):
    p = GeminiProvider("g-key", "gemini-2.5-pro")
    assert p._config(64, False).thinking_config is None


def test_complete_maps_json_mode_and_relaxes_safety(fake_genai):
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    assert p.complete("hello", max_tokens=77, json_mode=True) == "hi"
    call = p._client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "hello"
    cfg = call["config"]
    assert cfg.max_output_tokens == 77
    assert cfg.response_mime_type == "application/json"
    cats = {str(s.category) for s in cfg.safety_settings}
    assert any("HARASSMENT" in c for c in cats)
    assert any("DANGEROUS" in c for c in cats)
    assert all("BLOCK_NONE" in str(s.threshold) for s in cfg.safety_settings)


def test_complete_without_json_mode_leaves_mime_unset(fake_genai):
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    p.complete("hello", max_tokens=10, json_mode=False)
    assert p._client.models.calls[0]["config"].response_mime_type is None


def test_empty_candidate_reports_finish_reason(fake_genai):
    cand = types.SimpleNamespace(finish_reason="SAFETY")
    fake_genai(_Resp(text=None, candidates=[cand]))
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "empty"
    assert "SAFETY" in str(ei.value)


def test_prompt_blocked_reports_block_reason(fake_genai):
    fb = types.SimpleNamespace(block_reason="PROHIBITED_CONTENT")
    fake_genai(_Resp(text=None, candidates=[], prompt_feedback=fb, text_raises=True))
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "empty"
    assert "PROHIBITED_CONTENT" in str(ei.value)


def test_api_error_401_maps_to_auth(fake_genai):
    from google.genai import errors

    exc = errors.APIError(401, {"error": {"message": "bad key", "status": "UNAUTHENTICATED"}})
    fake_genai(exc)
    p = GeminiProvider("g-bad", "gemini-2.5-flash")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "auth"


def test_api_error_other_maps_to_generic_with_code(fake_genai):
    from google.genai import errors

    exc = errors.APIError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}})
    fake_genai(exc)
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "error"
    assert "503" in str(ei.value)


def test_httpx_error_maps_to_network(fake_genai):
    fake_genai(httpx.ConnectError("boom"))
    p = GeminiProvider("g-key", "gemini-2.5-flash")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "network"
