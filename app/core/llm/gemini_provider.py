"""Google Gemini adapter via the google-genai SDK. Tk-free.

Safety settings are relaxed to BLOCK_NONE for the standard categories because
tabletop transcripts are full of violence and profanity; with the defaults the
API returns an empty candidate and we would rather have text than a blank.
"""

from __future__ import annotations

from app.core.llm.base import (
    auth_error,
    empty_error,
    generic_error,
    missing_key_error,
    network_error,
)

_TIMEOUT_MS = 120_000
_RELAXED_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)


class GeminiProvider:
    provider_id = "gemini"
    display_name = "Google Gemini"
    supports_json_mode = True

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise missing_key_error(self.provider_id, self.display_name)
        import httpx
        from google import genai
        from google.genai import errors, types

        self._types = types
        self._errors = errors
        self._httpx = httpx
        self.model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS)
        )

    def _config(self, max_tokens: int, json_mode: bool):
        t = self._types
        return t.GenerateContentConfig(
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else None,
            safety_settings=[
                t.SafetySetting(category=c, threshold="BLOCK_NONE") for c in _RELAXED_CATEGORIES
            ],
        )

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        try:
            resp = self._client.models.generate_content(
                model=self.model, contents=prompt, config=self._config(max_tokens, json_mode)
            )
        except self._errors.APIError as e:
            code = getattr(e, "code", None)
            if code in (401, 403):
                raise auth_error(self.provider_id, self.display_name) from e
            raise generic_error(
                self.provider_id, self.display_name, f"HTTP {code}: {getattr(e, 'message', e)}"
            ) from e
        except self._httpx.HTTPError as e:
            raise network_error(self.provider_id, self.display_name, type(e).__name__) from e

        try:
            text = resp.text
        except ValueError:  # google-genai raises when the response has no parts
            text = None
        if text and text.strip():
            return text

        detail = "unknown"
        feedback = getattr(resp, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            detail = f"blocked: {feedback.block_reason}"
        else:
            candidates = getattr(resp, "candidates", None) or []
            if candidates and getattr(candidates[0], "finish_reason", None):
                detail = f"finish reason: {candidates[0].finish_reason}"
        raise empty_error(self.provider_id, self.display_name, detail)
