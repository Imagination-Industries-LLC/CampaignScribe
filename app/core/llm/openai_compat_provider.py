"""OpenAI-compatible adapter (openai SDK + configurable base_url). Tk-free.

Serves OpenRouter, the Ollama / LM Studio local presets, and custom endpoints: same code, different base_url, model and timeout.
"""

from __future__ import annotations

from app.core.llm.base import (
    LLMError,
    auth_error,
    empty_error,
    generic_error,
    network_error,
)
from app.core.llm.local_detect import RUNTIME_NAMES

_TIMEOUT_TOTAL = 120.0
_MAX_RETRIES = 3
REPO_URL = "https://github.com/Imagination-Industries-LLC/CampaignScribe"


class OpenAICompatProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        provider_id: str,
        display_name: str,
        supports_json_mode: bool,
        timeout_s: float = _TIMEOUT_TOTAL,
        local_runtime: str = "",
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.supports_json_mode = supports_json_mode
        self.model = model
        self._local_runtime = local_runtime
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise LLMError(
                provider_id,
                f"Set the {display_name} base URL in Settings (⚙).",
                kind="missing_key",
            )
        self.base_url = base_url
        import openai

        self._openai = openai
        headers = None
        if provider_id == "openrouter":
            headers = {"HTTP-Referer": REPO_URL, "X-Title": "CampaignScribe"}
        self._client = openai.OpenAI(
            api_key=api_key
            or "sk-none",  # the SDK insists on a non-empty key; local servers ignore it
            base_url=base_url,
            timeout=timeout_s,
            max_retries=_MAX_RETRIES,
            default_headers=headers,
        )

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        o = self._openai
        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if json_mode and self.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except (o.AuthenticationError, o.PermissionDeniedError) as e:
            raise auth_error(self.provider_id, self.display_name) from e
        except o.APIConnectionError as e:
            if self._local_runtime:
                raise LLMError(
                    self.provider_id,
                    f"Could not reach {self.display_name} ({type(e).__name__}) — "
                    f"is {RUNTIME_NAMES.get(self._local_runtime, self.display_name)} running?",
                    kind="network",
                ) from e
            raise network_error(self.provider_id, self.display_name, type(e).__name__) from e
        except o.APIStatusError as e:
            detail = f"HTTP {e.status_code}"
            if self._local_runtime:
                body = e.body if isinstance(e.body, dict) else {}
                err = body.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or "")
                elif isinstance(err, str):
                    msg = err
                else:
                    msg = str(getattr(e, "message", "") or "")
                if msg:
                    detail += f": {msg}"
            raise generic_error(self.provider_id, self.display_name, detail) from e
        choices = getattr(resp, "choices", None) or []
        content = choices[0].message.content if choices else None
        if not content or not content.strip():
            reason = getattr(choices[0], "finish_reason", None) if choices else None
            raise empty_error(
                self.provider_id, self.display_name, f"finish reason: {reason or 'unknown'}"
            )
        return content
