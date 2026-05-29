"""Shared Anthropic client factory with sensible timeouts + retries.

Both speaker_id.py and summarizer.py build their client through make_client so
network-resilience policy lives in one place.
"""

from __future__ import annotations

# Generous total per-request budget (long generations) but a short connect
# timeout so a dead network fails fast instead of hanging the worker thread.
_TIMEOUT_TOTAL = 120.0
_TIMEOUT_CONNECT = 10.0

# The Anthropic SDK retries connection errors, 408/409/429 and 5xx with
# exponential backoff + jitter and honors Retry-After. It does NOT retry 401
# (auth) or other 4xx, which is exactly what we want. We just raise the count.
_MAX_RETRIES = 3


def make_client(api_key: str):
    if not api_key:
        raise RuntimeError("Anthropic API key not set. Open Settings (gear) to add it.")
    import anthropic
    import httpx

    return anthropic.Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(_TIMEOUT_TOTAL, connect=_TIMEOUT_CONNECT),
        max_retries=_MAX_RETRIES,
    )
