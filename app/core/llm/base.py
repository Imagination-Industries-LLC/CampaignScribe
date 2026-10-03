"""Provider protocol + the one error type the UI is allowed to see.

Every adapter wraps its SDK's exceptions into LLMError via the helpers below so
UI code never imports an LLM SDK. Tk-free.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

KINDS = ("missing_key", "auth", "network", "empty", "error")


@runtime_checkable
class Provider(Protocol):
    provider_id: str
    model: str
    display_name: str
    supports_json_mode: bool

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        """Single-turn text in -> text out. json_mode is a request, not a guarantee."""
        ...


class LLMError(RuntimeError):
    def __init__(self, provider_id: str, message: str, *, kind: str = "error") -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown LLMError kind: {kind!r}")
        super().__init__(message)
        self.provider_id = provider_id
        self.kind = kind


def missing_key_error(provider_id: str, display_name: str, detail: str = "") -> LLMError:
    return LLMError(
        provider_id, f"Add your {display_name} API key in Settings (⚙).", kind="missing_key"
    )


def auth_error(provider_id: str, display_name: str, detail: str = "") -> LLMError:
    return LLMError(
        provider_id, f"{display_name} rejected the API key. Check Settings (⚙).", kind="auth"
    )


def network_error(provider_id: str, display_name: str, detail: str = "") -> LLMError:
    suffix = f" ({detail})" if detail else ""
    return LLMError(provider_id, f"Could not reach {display_name}{suffix}.", kind="network")


def empty_error(provider_id: str, display_name: str, detail: str = "") -> LLMError:
    suffix = f" ({detail})" if detail else ""
    return LLMError(provider_id, f"{display_name} returned no text{suffix}.", kind="empty")


def generic_error(provider_id: str, display_name: str, detail: str = "") -> LLMError:
    suffix = f": {detail}" if detail else ""
    return LLMError(provider_id, f"{display_name} error{suffix}", kind="error")
