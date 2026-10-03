"""LLM provider abstraction: Claude / Gemini / OpenAI-compatible behind one protocol."""

from app.core.llm.base import LLMError, Provider

__all__ = ["LLMError", "Provider"]
