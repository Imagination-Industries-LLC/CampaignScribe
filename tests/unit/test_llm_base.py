"""Provider protocol + LLMError helpers (Tk-free, SDK-free)."""

from __future__ import annotations

import pytest

from app.core.llm import base


class _Scripted:
    provider_id = "scripted"
    model = "m"
    display_name = "Scripted"
    supports_json_mode = True

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        return "ok"


def test_runtime_checkable_protocol_accepts_duck_typed_provider():
    assert isinstance(_Scripted(), base.Provider)


def test_llmerror_carries_provider_and_kind():
    err = base.LLMError("gemini", "boom", kind="auth")
    assert str(err) == "boom"
    assert err.provider_id == "gemini"
    assert err.kind == "auth"
    assert isinstance(err, RuntimeError)


def test_llmerror_rejects_unknown_kind():
    with pytest.raises(ValueError):
        base.LLMError("x", "m", kind="weird")


@pytest.mark.parametrize(
    "fn, kind, needle",
    [
        (base.missing_key_error, "missing_key", "Add your Google Gemini API key in Settings"),
        (base.auth_error, "auth", "Google Gemini rejected the API key"),
        (base.network_error, "network", "Could not reach Google Gemini"),
        (base.empty_error, "empty", "Google Gemini returned no text"),
        (base.generic_error, "error", "Google Gemini error"),
    ],
)
def test_helpers_build_provider_named_messages(fn, kind, needle):
    err = fn("gemini", "Google Gemini", "detail here")
    assert err.kind == kind
    assert err.provider_id == "gemini"
    assert needle in str(err)
    if kind in ("network", "empty", "error"):
        assert "detail here" in str(err)
