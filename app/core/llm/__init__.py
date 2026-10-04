"""LLM provider abstraction: Claude / Gemini / OpenAI-compatible behind one protocol.

UI code imports only this module: `from app.core import llm` then
`llm.get_provider()`, `llm.provider_ready()`, `llm.not_ready_message()`,
`llm.active_preset()`, and catches `llm.LLMError`.
"""

from app.core.llm import cost, local_detect
from app.core.llm.base import LLMError, Provider
from app.core.llm.factory import (
    BASE_URLS,
    PRESETS,
    Preset,
    active_preset,
    badges_for,
    get_provider,
    make_provider,
    not_ready_message,
    provider_ready,
)

__all__ = [
    "BASE_URLS",
    "LLMError",
    "PRESETS",
    "Preset",
    "Provider",
    "active_preset",
    "badges_for",
    "cost",
    "get_provider",
    "local_detect",
    "make_provider",
    "not_ready_message",
    "provider_ready",
]
