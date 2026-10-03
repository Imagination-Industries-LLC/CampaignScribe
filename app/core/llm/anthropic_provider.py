"""Anthropic (Claude) adapter. Absorbs the former claude_api.make_client policy.

Uses anthropic.Timeout (not httpx.Timeout) so the same code runs on the
installed 0.x SDK and on the 1.x line, which rejects httpx objects. Tk-free.
"""

from __future__ import annotations

from app.core.llm.base import (
    auth_error,
    empty_error,
    generic_error,
    missing_key_error,
    network_error,
)

# Generous total per-request budget (long generations) but a short connect
# timeout so a dead network fails fast instead of hanging the worker thread.
_TIMEOUT_TOTAL = 120.0
_TIMEOUT_CONNECT = 10.0
# The SDK retries connection errors, 408/409/429 and 5xx with backoff and
# honours Retry-After; it does NOT retry 401 or other 4xx. We just raise the count.
_MAX_RETRIES = 3


class AnthropicProvider:
    provider_id = "anthropic"
    display_name = "Claude"
    supports_json_mode = False

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise missing_key_error(self.provider_id, self.display_name)
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=anthropic.Timeout(_TIMEOUT_TOTAL, connect=_TIMEOUT_CONNECT),
            max_retries=_MAX_RETRIES,
        )

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        a = self._anthropic
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except (a.AuthenticationError, a.PermissionDeniedError) as e:
            raise auth_error(self.provider_id, self.display_name) from e
        except a.APIConnectionError as e:  # includes APITimeoutError
            raise network_error(self.provider_id, self.display_name, type(e).__name__) from e
        except a.APIStatusError as e:
            raise generic_error(self.provider_id, self.display_name, f"HTTP {e.status_code}") from e
        text = "".join(
            getattr(block, "text", "")
            for block in getattr(resp, "content", [])
            if getattr(block, "type", "text") == "text"
        )
        if not text.strip():
            stop = getattr(resp, "stop_reason", None) or "unknown"
            raise empty_error(self.provider_id, self.display_name, f"stop reason: {stop}")
        return text
