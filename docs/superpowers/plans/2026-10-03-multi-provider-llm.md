# Multi-Provider LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick which LLM (Claude, Google Gemini, OpenRouter, or a custom OpenAI-compatible endpoint) powers speaker identification and summaries, with per-provider keys in Credential Manager and a Settings section to switch and test providers.

**Architecture:** A new Tk-free package `app/core/llm/` holds a `Provider` protocol, one adapter per API family (Anthropic, Gemini, OpenAI-compatible), a `PRESETS` table and a factory. `speaker_id.py` and `summarizer.py` stop importing the Anthropic SDK and call `provider.complete(prompt, max_tokens, json_mode)`. UI workers build one provider per run from config; pre-flight checks and the missing-key banner use `provider_ready()`. The Settings dialog gains an "AI model" section with a Test-connection button. PRIVACY.md and the in-app privacy notes name the active provider.

**Tech Stack:** Python 3.11, Tkinter/ttk, `anthropic` (0.109 installed; code must also run on 1.x), `google-genai`, `openai`, `keyring`, pytest. Windows + PowerShell 5.1; run everything through `.venv\Scripts\python`.

**Spec:** `docs/superpowers/specs/2026-10-03-multi-provider-llm-design.md` — read it first; this plan argues from it.

## Global Constraints

- Branch `feature/multi-provider-llm` off `main` (already created, spec committed). One PR at the end; Mike merges.
- Every commit: `.venv\Scripts\python -m ruff check .` and `.venv\Scripts\python -m ruff format .` clean first. Single-line commit messages. **No AI attribution, no `Co-Authored-By`.**
- Tests: `.venv\Scripts\python -m pytest -q` (full) must stay green after every task. Unit tests are Tk-free; GUI tests carry `pytestmark = pytest.mark.gui` and the per-file `root` fixture pattern shown in Task 8.
- No change to the ML pins in `requirements.txt` (`torch`, `torchaudio`, `whisperx`, `pyannote.audio`, `transformers`, `huggingface_hub`, `lightning`, `pytorch-lightning`, `faster-whisper`). `.github/dependabot.yml` is not touched.
- Default Anthropic model id is exactly `claude-sonnet-5-5`. Model ids live in config defaults, never in code constants outside `factory.PRESETS`.
- Anthropic adapter must use `anthropic.Timeout`, never `httpx.Timeout` (1.x SDK rejects httpx objects).
- Keyring usernames: `llm_key_<provider_id>`; the legacy `anthropic_api_key` entry is read as a fallback and **never written or deleted**.
- No references to the predecessor product name anywhere. Every `subprocess` call (none expected in this feature) uses `CREATE_NO_WINDOW`.
- UI code never imports an LLM SDK; it only sees `LLMError`.

## Review Focus

Inputs the spec implies but did not spell out; each has a pinned test in the owning task:

1. A hand-edited `config.json` with `"llm_provider": "banana"` must still run on Anthropic and log the fallback, not crash at the first Transcribe. → Task 5 `test_get_provider_unknown_id_falls_back_to_anthropic`.
2. A custom base URL pasted with a trailing slash or surrounding whitespace (`" http://localhost:11434/v1/ "`) must produce a working client URL. → Task 4 `test_base_url_is_normalised`, Task 8 `test_save_strips_base_url`.
3. An API key pasted with a trailing newline or spaces must be stored stripped, or every call fails with a confusing 401. → Task 5 `test_save_provider_key_strips_whitespace`.
4. Gemini blocking the **prompt** (no candidates at all, `prompt_feedback.block_reason` set) must surface as a readable "returned no text (blocked: …)" error, not an `AttributeError` on `candidates[0]`. → Task 3 `test_prompt_blocked_reports_block_reason`.
5. Clicking Test connection and closing the dialog before the thread returns must not raise `TclError` from the worker's `after` callback. → Task 8 `test_test_connection_result_after_destroy_is_ignored`.

---

### Task 1: `app/core/llm` package — `Provider` protocol, `LLMError`, dev dependencies

**Files:**
- Create: `app/core/llm/__init__.py`
- Create: `app/core/llm/base.py`
- Modify: `requirements-dev.txt` (add two floors)
- Test: `tests/unit/test_llm_base.py`

**Interfaces:**
- Produces: `app.core.llm.base.Provider` (Protocol with `provider_id: str`, `model: str`, `display_name: str`, `supports_json_mode: bool`, `complete(prompt: str, max_tokens: int, json_mode: bool = False) -> str`), `LLMError(provider_id, message, *, kind)` with `.provider_id`, `.kind`, and the five helpers `missing_key_error`, `auth_error`, `network_error`, `empty_error`, `generic_error` (all `(provider_id: str, display_name: str, detail: str = "") -> LLMError`). Later tasks raise only through these helpers.

- [ ] **Step 1: Install the two new SDKs into the venv and record floors**

Run (PowerShell):
```
.venv\Scripts\python -m pip install google-genai openai
.venv\Scripts\python -m pip show google-genai openai | Select-String "^Version"
```
Append to `requirements-dev.txt` (keep the file's existing style of `>=` floors; use the versions pip just printed, expected `google-genai>=2.28.0` and `openai>=3.24.0`):
```
google-genai>=2.28.0
openai>=3.24.0
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_llm_base.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.llm'`

- [ ] **Step 4: Implement `base.py` and the package init**

Create `app/core/llm/base.py`:
```python
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
```

Create `app/core/llm/__init__.py` (the factory names are added in Task 5; for now only the base symbols):
```python
"""LLM provider abstraction: Claude / Gemini / OpenAI-compatible behind one protocol."""

from app.core.llm.base import LLMError, Provider

__all__ = ["LLMError", "Provider"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_base.py -v`
Expected: 8 PASS

- [ ] **Step 6: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm requirements-dev.txt tests/unit/test_llm_base.py
git commit -m "feat(llm): Provider protocol, LLMError and message helpers; add google-genai/openai dev floors"
```

---

### Task 2: `AnthropicProvider`

**Files:**
- Create: `app/core/llm/anthropic_provider.py`
- Test: `tests/unit/test_llm_anthropic.py`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `AnthropicProvider(api_key: str, model: str)` with `provider_id="anthropic"`, `display_name="Claude"`, `supports_json_mode=False`, `complete(...)`. Module constants `_TIMEOUT_TOTAL = 120.0`, `_TIMEOUT_CONNECT = 10.0`, `_MAX_RETRIES = 3` (Task 5's factory and the existing `claude_api` policy agree on these).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_anthropic.py`:
```python
"""AnthropicProvider: client policy, text extraction, error mapping (fake SDK client)."""

from __future__ import annotations

import httpx
import pytest

from app.core.llm import base
from app.core.llm.anthropic_provider import AnthropicProvider


class _Block:
    def __init__(self, text, type_="text"):
        self.text = text
        self.type = type_


class _Resp:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content = blocks
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patch anthropic.Anthropic with a capturing fake; returns a setter for the outcome."""
    import anthropic

    captured = {}
    state = {"outcome": _Resp([_Block("hi")])}

    class _Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.messages = _Messages(state["outcome"])

    monkeypatch.setattr(anthropic, "Anthropic", _Fake)

    def _set(outcome):
        state["outcome"] = outcome

    _set.captured = captured
    return _set


def test_empty_key_raises_missing_key():
    with pytest.raises(base.LLMError) as ei:
        AnthropicProvider("", "claude-sonnet-5-5")
    assert ei.value.kind == "missing_key"
    assert "Claude" in str(ei.value)


def test_client_uses_anthropic_timeout_and_retries(fake_anthropic):
    import anthropic

    AnthropicProvider("sk-test", "claude-sonnet-5-5")
    cap = fake_anthropic.captured
    assert cap["api_key"] == "sk-test"
    assert cap["max_retries"] == 3
    assert isinstance(cap["timeout"], anthropic.Timeout)
    assert cap["timeout"].connect == 10.0
    assert cap["timeout"].read == 120.0


def test_complete_sends_model_and_prompt_and_joins_text_blocks(fake_anthropic):
    fake_anthropic(_Resp([_Block("part one "), _Block("ignored", "tool_use"), _Block("part two")]))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    out = p.complete("hello", max_tokens=55, json_mode=True)
    assert out == "part one part two"
    call = p._client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] == 55
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert "response_format" not in call  # prompt-level JSON only


def test_refusal_or_blank_response_is_empty_error(fake_anthropic):
    fake_anthropic(_Resp([], stop_reason="refusal"))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "empty"
    assert "refusal" in str(ei.value)


def test_auth_error_maps_to_auth_kind(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError(
        "bad key", response=httpx.Response(401, request=req), body=None
    )
    fake_anthropic(exc)
    p = AnthropicProvider("sk-bad", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "auth"


def test_connection_error_maps_to_network_kind(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_anthropic(anthropic.APIConnectionError(request=req))
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "network"


def test_other_status_error_maps_to_generic_with_code(fake_anthropic):
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIStatusError("boom", response=httpx.Response(529, request=req), body=None)
    fake_anthropic(exc)
    p = AnthropicProvider("sk-test", "claude-sonnet-5-5")
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=10)
    assert ei.value.kind == "error"
    assert "529" in str(ei.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_anthropic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.llm.anthropic_provider'`

- [ ] **Step 3: Implement the adapter**

Create `app/core/llm/anthropic_provider.py`:
```python
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
            raise generic_error(
                self.provider_id, self.display_name, f"HTTP {e.status_code}"
            ) from e
        text = "".join(
            getattr(block, "text", "")
            for block in getattr(resp, "content", [])
            if getattr(block, "type", "text") == "text"
        )
        if not text.strip():
            stop = getattr(resp, "stop_reason", None) or "unknown"
            raise empty_error(self.provider_id, self.display_name, f"stop reason: {stop}")
        return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_anthropic.py -v`
Expected: 7 PASS

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/anthropic_provider.py tests/unit/test_llm_anthropic.py
git commit -m "feat(llm): AnthropicProvider adapter with anthropic.Timeout policy and LLMError mapping"
```

---

### Task 3: `GeminiProvider`

**Files:**
- Create: `app/core/llm/gemini_provider.py`
- Test: `tests/unit/test_llm_gemini.py`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `GeminiProvider(api_key: str, model: str)` with `provider_id="gemini"`, `display_name="Google Gemini"`, `supports_json_mode=True`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_gemini.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_gemini.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.llm.gemini_provider'`

- [ ] **Step 3: Implement the adapter**

Create `app/core/llm/gemini_provider.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_gemini.py -v`
Expected: 9 PASS. If `errors.APIError(code, body)` has a different constructor in the installed google-genai, read `.venv\Lib\site-packages\google\genai\errors.py` and adjust the two test constructions to match (the adapter only reads `.code` and `.message`).

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/gemini_provider.py tests/unit/test_llm_gemini.py
git commit -m "feat(llm): GeminiProvider adapter (google-genai) with JSON mode and relaxed safety settings"
```

---

### Task 4: `OpenAICompatProvider`

**Files:**
- Create: `app/core/llm/openai_compat_provider.py`
- Test: `tests/unit/test_llm_openai_compat.py`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `OpenAICompatProvider(api_key: str, model: str, base_url: str, *, provider_id: str, display_name: str, supports_json_mode: bool)`; attribute `base_url` (normalised). Module constant `REPO_URL = "https://github.com/Imagination-Industries-LLC/CampaignScribe"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_openai_compat.py`:
```python
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
    return OpenAICompatProvider(
        kw.pop("api_key"), kw.pop("model"), kw.pop("base_url"), **kw
    )


def test_missing_base_url_is_missing_key_kind(fake_openai):
    with pytest.raises(base.LLMError) as ei:
        _make(fake_openai, base_url="", provider_id="custom", display_name="Custom endpoint")
    assert ei.value.kind == "missing_key"
    assert "base URL" in str(ei.value)


def test_base_url_is_normalised(fake_openai):
    p = _make(fake_openai, base_url="  http://localhost:11434/v1/  ", provider_id="custom",
              display_name="Custom endpoint", supports_json_mode=False)
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
    exc = openai.AuthenticationError(
        "bad", response=httpx.Response(401, request=req), body=None
    )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_openai_compat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.llm.openai_compat_provider'`

- [ ] **Step 3: Implement the adapter**

Create `app/core/llm/openai_compat_provider.py`:
```python
"""OpenAI-compatible adapter (openai SDK + configurable base_url). Tk-free.

Serves OpenRouter in v1 and is the bridge to OpenAI / Groq / DeepSeek and local
servers (Ollama, LM Studio) later: same code, different base_url and model.
"""

from __future__ import annotations

from app.core.llm.base import (
    LLMError,
    auth_error,
    empty_error,
    generic_error,
    network_error,
)

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
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.supports_json_mode = supports_json_mode
        self.model = model
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
            api_key=api_key or "sk-none",  # the SDK insists on a non-empty key; local servers ignore it
            base_url=base_url,
            timeout=_TIMEOUT_TOTAL,
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
            raise network_error(self.provider_id, self.display_name, type(e).__name__) from e
        except o.APIStatusError as e:
            raise generic_error(
                self.provider_id, self.display_name, f"HTTP {e.status_code}"
            ) from e
        choices = getattr(resp, "choices", None) or []
        content = choices[0].message.content if choices else None
        if not content or not content.strip():
            reason = getattr(choices[0], "finish_reason", None) if choices else None
            raise empty_error(
                self.provider_id, self.display_name, f"finish reason: {reason or 'unknown'}"
            )
        return content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_openai_compat.py -v`
Expected: 10 PASS

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/openai_compat_provider.py tests/unit/test_llm_openai_compat.py
git commit -m "feat(llm): OpenAICompatProvider adapter for OpenRouter and custom endpoints"
```

---

### Task 5: Presets, factory, config keys and per-provider keyring

**Files:**
- Create: `app/core/llm/factory.py`
- Modify: `app/core/llm/__init__.py`
- Modify: `app/config.py` (`DEFAULT_CONFIG` + four key functions)
- Test: `tests/unit/test_llm_factory.py`, `tests/unit/test_config_llm.py`

**Interfaces:**
- Consumes: Tasks 2–4 adapters.
- Produces (all re-exported from `app.core.llm`): `Preset` dataclass (`provider_id, display_name, vendor_label, default_model, needs_key, needs_base_url, supports_json_mode, privacy_url`), `PRESETS: dict[str, Preset]` in dropdown order, `BASE_URLS = {"openrouter": "https://openrouter.ai/api/v1"}`, `make_provider(provider_id, *, model, api_key, base_url="") -> Provider`, `get_provider(cfg=None) -> Provider`, `active_preset(cfg=None) -> Preset`, `provider_ready(cfg=None) -> bool`, `not_ready_message(cfg=None) -> str`. In `app.config`: `save_provider_key(provider_id, key)`, `get_provider_key(provider_id) -> str`, plus the six new `DEFAULT_CONFIG` keys.

- [ ] **Step 1: Write the failing config tests**

Create `tests/unit/test_config_llm.py`:
```python
"""config: llm_* defaults merge into old configs; per-provider keyring + legacy fallback."""

from __future__ import annotations

import json

import keyring

from app import config


def test_new_llm_defaults_merge_into_old_config_json():
    p = config.get_config_path()
    p.write_text(json.dumps({"theme_mode": "light"}), encoding="utf-8")
    cfg = config.load_config()
    assert cfg["theme_mode"] == "light"
    assert cfg["llm_provider"] == "anthropic"
    assert cfg["llm_model_anthropic"] == "claude-sonnet-5-5"
    assert cfg["llm_model_gemini"] == "gemini-2.5-flash"
    assert cfg["llm_model_openrouter"] == "anthropic/claude-sonnet-4.5"
    assert cfg["llm_model_custom"] == ""
    assert cfg["llm_base_url_custom"] == ""


def test_provider_key_roundtrip_per_provider():
    config.save_provider_key("gemini", "g-1")
    config.save_provider_key("openrouter", "or-1")
    assert config.get_provider_key("gemini") == "g-1"
    assert config.get_provider_key("openrouter") == "or-1"
    assert config.get_provider_key("custom") == ""
    assert keyring.get_password(config.SERVICE_NAME, "llm_key_gemini") == "g-1"


def test_save_provider_key_strips_whitespace():
    config.save_provider_key("gemini", "  g-2\n")
    assert config.get_provider_key("gemini") == "g-2"


def test_anthropic_legacy_entry_is_read_as_fallback_but_never_written():
    keyring.set_password(config.SERVICE_NAME, "anthropic_api_key", "legacy-key")
    assert config.get_provider_key("anthropic") == "legacy-key"
    assert config.get_anthropic_key() == "legacy-key"

    config.save_anthropic_key("new-key")
    assert config.get_provider_key("anthropic") == "new-key"
    assert keyring.get_password(config.SERVICE_NAME, "llm_key_anthropic") == "new-key"
    assert keyring.get_password(config.SERVICE_NAME, "anthropic_api_key") == "legacy-key"


def test_explicitly_blank_new_key_falls_back_to_legacy():
    keyring.set_password(config.SERVICE_NAME, "anthropic_api_key", "legacy-key")
    config.save_provider_key("anthropic", "")
    assert config.get_provider_key("anthropic") == "legacy-key"
```

- [ ] **Step 2: Write the failing factory tests**

Create `tests/unit/test_llm_factory.py`:
```python
"""factory: presets, make_provider/get_provider wiring, readiness checks, unknown-id fallback."""

from __future__ import annotations

import pytest

from app import config
from app.core import llm
from app.core.llm import factory


@pytest.fixture(autouse=True)
def _stub_sdks(monkeypatch):
    """Keep the SDK constructors from doing anything (the adapters import lazily)."""
    import anthropic
    import openai
    from google import genai

    class _Dummy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(anthropic, "Anthropic", _Dummy)
    monkeypatch.setattr(genai, "Client", _Dummy)
    monkeypatch.setattr(openai, "OpenAI", _Dummy)


def test_presets_order_and_shape():
    assert list(llm.PRESETS) == ["anthropic", "gemini", "openrouter", "custom"]
    a = llm.PRESETS["anthropic"]
    assert a.display_name == "Claude"
    assert a.default_model == "claude-sonnet-5-5"
    assert a.needs_key and not a.needs_base_url and not a.supports_json_mode
    c = llm.PRESETS["custom"]
    assert c.needs_base_url and not c.needs_key and not c.supports_json_mode
    assert llm.PRESETS["openrouter"].supports_json_mode
    for p in llm.PRESETS.values():
        assert p.vendor_label
        if p.provider_id != "custom":
            assert p.privacy_url.startswith("https://")


def test_make_provider_each_preset():
    p = llm.make_provider("anthropic", model="claude-sonnet-5-5", api_key="k")
    assert p.provider_id == "anthropic" and p.model == "claude-sonnet-5-5"
    g = llm.make_provider("gemini", model="gemini-2.5-flash", api_key="k")
    assert g.provider_id == "gemini"
    o = llm.make_provider("openrouter", model="m", api_key="k")
    assert o.provider_id == "openrouter" and o.base_url == llm.BASE_URLS["openrouter"]
    assert o.display_name == "OpenRouter" and o.supports_json_mode
    c = llm.make_provider("custom", model="llama3", api_key="", base_url="http://localhost:11434/v1/")
    assert c.provider_id == "custom" and c.base_url == "http://localhost:11434/v1"
    assert not c.supports_json_mode


def test_make_provider_unknown_id_raises():
    with pytest.raises(ValueError):
        llm.make_provider("banana", model="x", api_key="k")


def test_get_provider_reads_config_and_keyring():
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    cfg["llm_model_gemini"] = "gemini-2.5-pro"
    config.save_config(cfg)
    config.save_provider_key("gemini", "g-key")
    p = llm.get_provider()
    assert p.provider_id == "gemini"
    assert p.model == "gemini-2.5-pro"


def test_get_provider_blank_model_uses_preset_default():
    cfg = config.load_config()
    cfg["llm_model_anthropic"] = "   "
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    assert llm.get_provider().model == "claude-sonnet-5-5"


def test_get_provider_unknown_id_falls_back_to_anthropic(monkeypatch):
    logged = []
    monkeypatch.setattr(config, "log_exception", lambda ctx, exc: logged.append((ctx, str(exc))))
    cfg = config.load_config()
    cfg["llm_provider"] = "banana"
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    p = llm.get_provider()
    assert p.provider_id == "anthropic"
    assert logged and "banana" in logged[0][1]
    assert llm.active_preset().provider_id == "anthropic"


def test_get_provider_missing_key_raises_llmerror():
    with pytest.raises(llm.LLMError) as ei:
        llm.get_provider()
    assert ei.value.kind == "missing_key"


@pytest.mark.parametrize(
    "provider, key, base_url, model, ready",
    [
        ("anthropic", "", "", "", False),
        ("anthropic", "k", "", "", True),
        ("gemini", "", "", "", False),
        ("gemini", "k", "", "", True),
        ("openrouter", "k", "", "", True),
        ("custom", "", "", "llama3", False),
        ("custom", "", "http://localhost:11434/v1", "", False),
        ("custom", "", "http://localhost:11434/v1", "llama3", True),
    ],
)
def test_provider_ready_truth_table(provider, key, base_url, model, ready):
    cfg = config.load_config()
    cfg["llm_provider"] = provider
    cfg["llm_base_url_custom"] = base_url
    cfg["llm_model_custom"] = model
    config.save_config(cfg)
    if key:
        config.save_provider_key(provider, key)
    assert llm.provider_ready() is ready


def test_not_ready_message_names_provider_or_base_url():
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    assert llm.not_ready_message() == "Add your Google Gemini API key in Settings (⚙)."
    cfg["llm_provider"] = "custom"
    config.save_config(cfg)
    assert llm.not_ready_message() == "Set the Custom endpoint base URL and model in Settings (⚙)."
    config.save_provider_key("anthropic", "k")
    cfg["llm_provider"] = "anthropic"
    config.save_config(cfg)
    assert llm.not_ready_message() == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_config_llm.py tests/unit/test_llm_factory.py -v`
Expected: FAIL (`AttributeError: module 'app.config' has no attribute 'save_provider_key'`, `ImportError` on `factory`)

- [ ] **Step 4: Add config keys and keyring functions**

In `app/config.py`, append to `DEFAULT_CONFIG` (after the `"crash_reporting_enabled"` line, inside the dict):
```python
    # ---- LLM provider (Multi-Provider LLM, Phase 2) ----
    "llm_provider": "anthropic",  # one of app.core.llm.PRESETS
    "llm_model_anthropic": "claude-sonnet-5-5",
    "llm_model_gemini": "gemini-2.5-flash",
    "llm_model_openrouter": "anthropic/claude-sonnet-4.5",
    "llm_model_custom": "",
    "llm_base_url_custom": "",
```

Replace the two Anthropic key functions with:
```python
_LEGACY_ANTHROPIC_USERNAME = "anthropic_api_key"


def _provider_key_username(provider_id: str) -> str:
    return f"llm_key_{provider_id}"


def save_provider_key(provider_id: str, key: str) -> None:
    """Store an LLM provider's API key in Credential Manager (stripped; '' clears)."""
    keyring.set_password(SERVICE_NAME, _provider_key_username(provider_id), (key or "").strip())


def get_provider_key(provider_id: str) -> str:
    """Read an LLM provider's key. For 'anthropic', fall back to the pre-Phase-2
    'anthropic_api_key' entry so existing installs keep working; that legacy
    entry is read-only (never written or deleted here)."""
    val = keyring.get_password(SERVICE_NAME, _provider_key_username(provider_id)) or ""
    if not val and provider_id == "anthropic":
        val = keyring.get_password(SERVICE_NAME, _LEGACY_ANTHROPIC_USERNAME) or ""
    return val


def save_anthropic_key(key: str) -> None:
    save_provider_key("anthropic", key)


def get_anthropic_key() -> str:
    return get_provider_key("anthropic")
```

- [ ] **Step 5: Implement the factory**

Create `app/core/llm/factory.py`:
```python
"""Preset table + factory: config/keyring -> a ready Provider. Tk-free."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import config
from app.core.llm.base import LLMError, Provider


@dataclass(frozen=True)
class Preset:
    provider_id: str
    display_name: str  # dropdown + error messages
    vendor_label: str  # "Sent to <vendor_label>" in privacy notes
    default_model: str
    needs_key: bool
    needs_base_url: bool
    supports_json_mode: bool
    privacy_url: str


PRESETS: dict[str, Preset] = {
    "anthropic": Preset(
        "anthropic", "Claude", "Anthropic (Claude)", "claude-sonnet-5-5",
        True, False, False, "https://www.anthropic.com/legal/privacy",
    ),
    "gemini": Preset(
        "gemini", "Google Gemini", "Google (Gemini)", "gemini-2.5-flash",
        True, False, True, "https://ai.google.dev/gemini-api/terms",
    ),
    "openrouter": Preset(
        "openrouter", "OpenRouter", "OpenRouter (which forwards it to the model vendor you chose)",
        "anthropic/claude-sonnet-4.5", True, False, True, "https://openrouter.ai/privacy",
    ),
    "custom": Preset(
        "custom", "Custom endpoint", "the custom endpoint you configured", "",
        False, True, False, "",
    ),
}

BASE_URLS = {"openrouter": "https://openrouter.ai/api/v1"}


def make_provider(provider_id: str, *, model: str, api_key: str, base_url: str = "") -> Provider:
    """Build an adapter from explicit values (Settings → Test connection uses unsaved ones)."""
    preset = PRESETS.get(provider_id)
    if preset is None:
        raise ValueError(f"unknown LLM provider: {provider_id!r}")
    model = (model or "").strip() or preset.default_model
    if provider_id == "anthropic":
        from app.core.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key, model)
    if provider_id == "gemini":
        from app.core.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key, model)
    from app.core.llm.openai_compat_provider import OpenAICompatProvider

    return OpenAICompatProvider(
        api_key,
        model,
        BASE_URLS.get(provider_id, base_url),
        provider_id=provider_id,
        display_name=preset.display_name,
        supports_json_mode=preset.supports_json_mode,
    )


def _cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return cfg if cfg is not None else config.load_config()


def _resolve_id(cfg: dict[str, Any]) -> str:
    pid = cfg.get("llm_provider", "anthropic")
    if pid not in PRESETS:
        config.log_exception(
            "llm.factory: unknown llm_provider in config, falling back to anthropic",
            ValueError(repr(pid)),
        )
        return "anthropic"
    return pid


def active_preset(cfg: dict[str, Any] | None = None) -> Preset:
    return PRESETS[_resolve_id(_cfg(cfg))]


def get_provider(cfg: dict[str, Any] | None = None) -> Provider:
    """The configured provider. Raises LLMError(kind='missing_key') when not set up."""
    c = _cfg(cfg)
    pid = _resolve_id(c)
    return make_provider(
        pid,
        model=c.get(f"llm_model_{pid}", ""),
        api_key=config.get_provider_key(pid),
        base_url=c.get("llm_base_url_custom", ""),
    )


def provider_ready(cfg: dict[str, Any] | None = None) -> bool:
    return not_ready_message(cfg) == ""


def not_ready_message(cfg: dict[str, Any] | None = None) -> str:
    """'' when the active provider can run; otherwise the sentence to show the user."""
    c = _cfg(cfg)
    preset = PRESETS[_resolve_id(c)]
    if preset.needs_base_url:
        base_url = (c.get("llm_base_url_custom", "") or "").strip()
        model = (c.get(f"llm_model_{preset.provider_id}", "") or "").strip()
        if not base_url or not model:
            return f"Set the {preset.display_name} base URL and model in Settings (⚙)."
    if preset.needs_key and not config.get_provider_key(preset.provider_id):
        return f"Add your {preset.display_name} API key in Settings (⚙)."
    return ""


__all__ = [
    "BASE_URLS",
    "LLMError",
    "PRESETS",
    "Preset",
    "active_preset",
    "get_provider",
    "make_provider",
    "not_ready_message",
    "provider_ready",
]
```

Replace `app/core/llm/__init__.py` with:
```python
"""LLM provider abstraction: Claude / Gemini / OpenAI-compatible behind one protocol.

UI code imports only this module: `from app.core import llm` then
`llm.get_provider()`, `llm.provider_ready()`, `llm.not_ready_message()`,
`llm.active_preset()`, and catches `llm.LLMError`.
"""

from app.core.llm.base import LLMError, Provider
from app.core.llm.factory import (
    BASE_URLS,
    PRESETS,
    Preset,
    active_preset,
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
    "get_provider",
    "make_provider",
    "not_ready_message",
    "provider_ready",
]
```

- [ ] **Step 6: Run the new tests and the whole suite**

Run: `.venv\Scripts\python -m pytest tests/unit/test_config_llm.py tests/unit/test_llm_factory.py tests/unit/test_config.py -v`
Expected: all PASS (the pre-existing `test_anthropic_key_roundtrip_via_keyring` still passes through the aliases).
Run: `.venv\Scripts\python -m pytest -q`
Expected: all PASS.

- [ ] **Step 7: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm app/config.py tests/unit/test_config_llm.py tests/unit/test_llm_factory.py
git commit -m "feat(llm): presets, factory, llm_* config keys and per-provider keyring with legacy Anthropic fallback"
```

---

### Task 6: Core refactor — `speaker_id` and `summarizer` take a `Provider`; delete `claude_api`; `fake_provider` fixture

**Files:**
- Modify: `app/core/speaker_id.py:1-60, 103-118, 145-168, 259-283`
- Modify: `app/core/summarizer.py:1-18, 28-66, 69-108, 122-129`
- Delete: `app/core/claude_api.py`, `tests/unit/test_claude_api.py`
- Modify: `tests/conftest.py:58-95` (replace `fake_claude`)
- Modify: `tests/unit/test_summarizer.py`, `tests/unit/test_summarizer_npcs.py`, `tests/integration/test_pipeline.py`
- Test: `tests/unit/test_speaker_id_provider.py` (new)

**Interfaces:**
- Consumes: `app.core.llm.Provider`, `LLMError`.
- Produces: `speaker_id.discover_speakers(segments, provider)`, `speaker_id.identify_speakers(segments, speakers_reference, provider)`, `speaker_id.refine_speakers(segments, speakers_reference, provider)`, `speaker_id._send(provider, prompt, max_tokens=4000, json_mode=True)`; `summarizer.summarize_part(transcript_text, speakers_reference, summary_prompt, provider, part_number=1, known_npcs=None)`, `summarizer.consolidate_summaries(part_summaries, speakers_reference, provider, known_npcs=None)`, `summarizer.write_docx(..., model_used: str = "")`, `summarizer.model_label(provider) -> str` (`"<display_name> · <model>"`). Test fixture `fake_provider(responses, *, supports_json_mode=True) -> ScriptedProvider` whose `.calls` is a list of dicts `{"prompt", "max_tokens", "json_mode"}`; it also patches `app.core.llm.get_provider` and `app.core.llm.factory.get_provider` to return the same instance.

- [ ] **Step 1: Replace the test fixture**

In `tests/conftest.py`, update the module docstring bullet to:
```
- ``fake_provider`` installs a ScriptedProvider (queued canned text) and patches
  app.core.llm.get_provider to return it — no network, no SDK, no real key.
```
Replace everything from `# ---- fake Anthropic client ----` to the end of the `fake_claude` fixture with:
```python
# ---- scripted LLM provider ----
class ScriptedProvider:
    """Provider double: pops queued responses, records every call."""

    provider_id = "scripted"
    display_name = "Scripted"
    model = "scripted-1"

    def __init__(self, responses, supports_json_mode=True):
        self.responses = list(responses)
        self.supports_json_mode = supports_json_mode
        self.calls: list[dict] = []

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens, "json_mode": json_mode})
        if not self.responses:
            raise AssertionError("ScriptedProvider.complete called with no queued response")
        return self.responses.pop(0)


@pytest.fixture
def fake_provider(monkeypatch):
    """Returns a factory: ``p = fake_provider(["resp1", "resp2"])`` installs a
    ScriptedProvider as the app's active provider and returns it for assertions on ``.calls``."""

    def _install(responses, *, supports_json_mode=True):
        p = ScriptedProvider(responses, supports_json_mode=supports_json_mode)
        monkeypatch.setattr("app.core.llm.factory.get_provider", lambda cfg=None: p)
        monkeypatch.setattr("app.core.llm.get_provider", lambda cfg=None: p)
        return p

    return _install
```

- [ ] **Step 2: Update the existing tests to the new signatures**

`tests/unit/test_summarizer_npcs.py`: replace `_prompt_of` with
```python
def _prompt_of(provider) -> str:
    assert provider.calls, "provider.complete was never called"
    return provider.calls[0]["prompt"]
```
and in every test rename the fixture `fake_claude` → `fake_provider`, and replace the positional/keyword api-key argument (`"sk-test"`, `"sk"`) with the provider instance returned by the fixture. Example of the first test after the edit:
```python
def test_summarize_part_includes_known_npcs(fake_provider):
    provider = fake_provider(["a part summary"])
    summarizer.summarize_part(
        "TRANSCRIPT TEXT",
        {"campaign": "Strahd", "context": "", "players": []},
        "Summarize this session.",
        provider,
        part_number=1,
        known_npcs=["Strahd", "Ireena"],
    )
    assert "Known NPCs in this campaign: Strahd, Ireena" in _prompt_of(provider)
```
(Keep each test's existing assertions; only the fixture name, the provider argument and `_prompt_of` change.)

`tests/unit/test_summarizer.py`: the two `consolidate_summaries` tests become
```python
def test_consolidate_summaries_parses_name_and_body(fake_provider):
    provider = fake_provider(["SESSION NAME: Into the Mist\n\n## Recap\nThe party fled."])
    result = summarizer.consolidate_summaries(["part 1 summary"], {"campaign": "Strahd"}, provider)
    assert result["session_name"] == "Into the Mist"
    assert "The party fled." in result["body"]
    assert result["raw"].startswith("SESSION NAME:")
    assert not result["body"].startswith("SESSION NAME:")
    assert provider.calls[0]["json_mode"] is False
    assert provider.calls[0]["max_tokens"] == 4000


def test_consolidate_summaries_defaults_name_when_missing(fake_provider):
    provider = fake_provider(["No name header, just prose."])
    result = summarizer.consolidate_summaries(["p1"], {}, provider)
    assert result["session_name"] == "Session Summary"
```

`tests/integration/test_pipeline.py`: rename `fake_claude` → `fake_provider` in the three tests; pass `provider` instead of `api_key="sk-x"` / `"sk-x"`:
```python
    provider = fake_provider(['{"SPEAKER_00": "Josh (DM)", "SPEAKER_01": "Mike (Wellbrix)"}'])
    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, provider)
    assert provider.calls[0]["json_mode"] is True
```
```python
    provider = fake_provider(["the model rambled and returned no json"])
    mapping = speaker_id.identify_speakers(SEGMENTS, SPEAKERS_REF, provider)
```
```python
def test_summarize_then_consolidate(fake_provider):
    provider = fake_provider(
        [
            "## Part 1
The party entered the crypt.",
            "SESSION NAME: The Crypt

## Recap
All survived.",
        ]
    )
    transcript = "DM: You enter a crypt.

Mike: I draw my sword."
    part = summarizer.summarize_part(transcript, SPEAKERS_REF, "Summarize this.", provider, 1)
    assert "crypt" in part.lower()

    result = summarizer.consolidate_summaries([part], SPEAKERS_REF, provider)
    assert result["session_name"] == "The Crypt"
    assert len(provider.calls) == 2, (
        f"Expected 2 LLM calls (summarize_part + consolidate_summaries), got {len(provider.calls)}"
    )
    assert all(c["json_mode"] is False for c in provider.calls)
```
(Keep any other assertions that test already makes on `result`.)

Delete `tests/unit/test_claude_api.py` (`git rm`).

- [ ] **Step 3: Write the new speaker_id provider tests**

Create `tests/unit/test_speaker_id_provider.py`:
```python
"""speaker_id routes every LLM call through provider.complete with json_mode=True."""

from __future__ import annotations

from app.core import speaker_id

SEGMENTS = [
    {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Roll initiative."},
    {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01", "text": "Natural twenty!"},
]


def test_discover_uses_json_mode_and_fills_defaults(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=30: {"SPEAKER_00": ["a"], "SPEAKER_01": ["b"]},
    )
    provider = fake_provider(['{"profiles": [{"source_speaker_id": "SPEAKER_00"}]}'])
    out = speaker_id.discover_speakers(SEGMENTS, provider)
    assert out["profiles"][0]["source_speaker_id"] == "SPEAKER_00"
    assert out["num_speakers_detected"] == 2
    call = provider.calls[0]
    assert call["json_mode"] is True
    assert call["max_tokens"] == 4000


def test_identify_requests_1000_tokens_json(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=15: {"SPEAKER_00": ["a"]},
    )
    provider = fake_provider(['{"SPEAKER_00": "DM"}'])
    assert speaker_id.identify_speakers(SEGMENTS, {"players": []}, provider) == {
        "SPEAKER_00": "DM"
    }
    assert provider.calls[0] == {
        "prompt": provider.calls[0]["prompt"],
        "max_tokens": 1000,
        "json_mode": True,
    }


def test_refine_falls_back_to_empty_lists_on_garbage(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.core.transcriber.collect_speaker_samples",
        lambda segments, max_lines=20: {"SPEAKER_00": ["a"]},
    )
    provider = fake_provider(["not json at all"])
    out = speaker_id.refine_speakers(SEGMENTS, {"players": []}, provider)
    assert out == {"improvements": [], "new_speakers": [], "suggested_ignores": []}
    assert provider.calls[0]["json_mode"] is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_speaker_id_provider.py tests/unit/test_summarizer.py tests/unit/test_summarizer_npcs.py tests/integration/test_pipeline.py -v`
Expected: FAIL (`AttributeError: 'ScriptedProvider' object has no attribute 'messages'` or similar — core still builds an Anthropic client).

- [ ] **Step 5: Refactor `speaker_id.py`**

Replace lines 1–21 (docstring through `_client`) with:
```python
"""LLM helpers for speaker discovery, identification, and refinement.

Provider-agnostic: every call goes through app.core.llm.Provider.complete with
json_mode=True; the prompts ask for JSON and _extract_json_object tolerates
fences and prose for providers without a native JSON mode.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core import transcriber as _transcriber
from app.core.llm.base import Provider
```
Replace `_send` with:
```python
def _send(provider: Provider, prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    return provider.complete(prompt, max_tokens=max_tokens, json_mode=json_mode)
```
In `_extract_json_object` change the two docstring/error mentions of "Claude" to "the model" (`"Could not parse JSON from the model response."`).
Change the three signatures and calls:
```python
def discover_speakers(segments: list[dict[str, Any]], provider: Provider) -> dict[str, Any]:
    ...
    raw = _send(provider, prompt, max_tokens=4000)
```
```python
def identify_speakers(
    segments: list[dict[str, Any]],
    speakers_reference: dict[str, Any],
    provider: Provider,
) -> dict[str, str]:
    ...
    raw = _send(provider, prompt, max_tokens=1000)
```
```python
def refine_speakers(
    segments: list[dict[str, Any]],
    speakers_reference: dict[str, Any],
    provider: Provider,
) -> dict[str, Any]:
    ...
    raw = _send(provider, prompt, max_tokens=4000)
```

- [ ] **Step 6: Refactor `summarizer.py`**

Replace lines 1–18 with:
```python
"""LLM summarization + .docx export (provider-agnostic)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.llm.base import Provider


def model_label(provider: Provider) -> str:
    """'<display name> · <model id>' for the .docx footer."""
    return f"{provider.display_name} · {provider.model}"
```
`summarize_part`: parameter `api_key: str` → `provider: Provider`; delete `client = _client(api_key)`; replace the `resp = client.messages.create(...)` / `return resp.content[0].text` block with
```python
    return provider.complete(full_prompt, max_tokens=4000, json_mode=False)
```
Update its docstring to "Run a single transcript part through the active LLM provider with the user's chosen prompt."
`consolidate_summaries`: `api_key: str` → `provider: Provider`; delete `client = _client(api_key)`; replace the create block with
```python
    text = provider.complete(prompt, max_tokens=4000, json_mode=False)
```
`write_docx`: `model_used: str = CLAUDE_MODEL` → `model_used: str = ""`, and in the meta line use `f"... | Model: {model_used or 'N/A'}"`.
`_render_summary_body` docstring: "Convert the LLM response body into Word headings, paragraphs and bullets."

Delete `app/core/claude_api.py` (`git rm`). Confirm nothing else imports it:
Run: `.venv\Scripts\python -m ruff check .` then `Select-String -Path app\**\*.py -Pattern "claude_api"` → no matches.

- [ ] **Step 7: Run the suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all PASS. (UI modules still pass `api_key` strings into these functions at runtime; that code path is only reachable with a live run and is fixed in Task 7. GUI tests do not execute the workers.)

- [ ] **Step 8: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add -A app/core tests/conftest.py tests/unit tests/integration
git commit -m "refactor(llm): speaker_id and summarizer call Provider.complete; drop claude_api; fake_provider fixture"
```

---

### Task 7: UI call sites — workers build a provider, pre-flight uses `provider_ready`, banner names the provider

**Files:**
- Modify: `app/ui/transcribe_tab.py:359-362, 399-401, 450, 487` (+ import)
- Modify: `app/ui/summarize_tab.py:394-396, 422-423, 442-449, 474-477, 493-507` (+ import)
- Modify: `app/ui/refine_tab.py:199-201, 207-209, 239` (+ import)
- Modify: `app/ui/edit_profile_window.py:343-349, 373` (+ import)
- Modify: `app/ui/app_window.py:105-120, 275-280`
- Test: `tests/gui/test_llm_preflight.py` (new)

**Interfaces:**
- Consumes: `app.core.llm` (`get_provider`, `provider_ready`, `not_ready_message`, `LLMError`), Task 6 signatures, `summarizer.model_label`.
- Produces: `AppWindow.banner_text` (the `ttk.Label` whose text is refreshed by `_refresh_banner`). Each tab keeps its `_start`/`_worker` names.

- [ ] **Step 1: Write the failing GUI tests**

Create `tests/gui/test_llm_preflight.py`:
```python
"""Pre-flight + banner use llm.provider_ready / not_ready_message; workers build one provider."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app import config

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "app.ui.app_window.check_gpu",
        lambda: {
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "error": "stub",
            "smi_gpu_name": None,
        },
    )
    from app.data import db

    db.init_db()
    try:
        from app.ui.app_window import AppWindow

        win = AppWindow()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    win.withdraw()
    win.update_idletasks()
    try:
        yield win
    finally:
        win.destroy()


def test_banner_names_active_provider_and_hides_when_ready(app):
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    app._refresh_banner()
    app.update_idletasks()
    assert "Google Gemini" in app.banner_text.cget("text")
    assert app.banner.winfo_manager() == "pack"

    config.save_provider_key("gemini", "g-key")
    app._refresh_banner()
    app.update_idletasks()
    assert app.banner.winfo_manager() == ""


def test_summarize_start_blocks_with_provider_message(root, monkeypatch):
    from app.ui.summarize_tab import SummarizeTab

    cfg = config.load_config()
    cfg["llm_provider"] = "openrouter"
    config.save_config(cfg)
    shown = []
    monkeypatch.setattr(
        "app.ui.summarize_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = SummarizeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.transcript_files = ["t.txt"]
    tab._start()
    assert shown == ["Add your OpenRouter API key in Settings (⚙)."]


def test_refine_start_blocks_with_provider_message(root, monkeypatch):
    from app.ui.refine_tab import RefineTab

    shown = []
    monkeypatch.setattr(
        "app.ui.refine_tab.messagebox.showerror", lambda title, msg, **k: shown.append(msg)
    )
    tab = RefineTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    tab.speakers_path = "x.json"
    tab.speakers_doc = {"players": []}
    tab.audio_files = ["a.wav"]
    tab._start()
    assert shown == ["Add your Claude API key in Settings (⚙)."]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_llm_preflight.py -v`
Expected: FAIL (`AttributeError: 'AppWindow' object has no attribute 'banner_text'`; the Summarize/Refine messages still say "Anthropic").

- [ ] **Step 3: `app_window.py` banner**

Replace lines 113–118 (the `ttk.Label(...)` through `self.banner_label = banner_inner`) with:
```python
        self.banner_text = ttk.Label(banner_inner, text="", style=LBL_STATUS_WARN)
        self.banner_text.pack(side="left")

        self.banner_label = banner_inner  # backwards-compatible attribute
```
Replace `_refresh_banner` with:
```python
    def _refresh_banner(self):
        msg = llm.not_ready_message()
        if not msg:
            self.banner.pack_forget()
        else:
            self.banner_text.config(text=f"⚠  {msg}")
            # Insert above notebook, below topbar
            self.banner.pack(side="top", fill="x", before=self.notebook)
```
Add `from app.core import library, llm, privacy` in place of the existing `from app.core import library, privacy` import.

- [ ] **Step 4: `transcribe_tab.py`**

Import: `from app.core import audio, library, llm, privacy, speaker_id, speakers_io, transcriber`.
Replace lines 359–362 with:
```python
        if not llm.provider_ready():
            messagebox.showerror("CampaignScribe", llm.not_ready_message())
            return
```
In `_worker`, replace `api_key = config.get_anthropic_key()` with:
```python
        try:
            provider = llm.get_provider()
        except llm.LLMError as e:
            self._set_status(str(e))
            self.after(0, lambda: self._set_busy(False))
            return
```
Replace `speaker_id.identify_speakers(segments, speakers_doc, api_key)` with `speaker_id.identify_speakers(segments, speakers_doc, provider)` and change the row label just above it from `"Claude speaker mapping"` to `f"{provider.display_name} speaker mapping"`. Replace `speaker_id.refine_speakers(all_segments, speakers_doc, api_key)` with `speaker_id.refine_speakers(all_segments, speakers_doc, provider)`.

- [ ] **Step 5: `summarize_tab.py`**

Import: `from app.core import library, llm, privacy, speakers_io, summarizer`.
Replace lines 394–396 with:
```python
        if not llm.provider_ready():
            messagebox.showerror("CampaignScribe", llm.not_ready_message())
            return
```
In `_worker(self, prompt_text)`, replace `api_key = config.get_anthropic_key()` with:
```python
        try:
            provider = llm.get_provider()
        except llm.LLMError as e:
            self._set_status(str(e))
            self.after(0, lambda: self._set_busy(False))
            return
```
and in the `summarizer.summarize_part(...)` call replace the `api_key,` argument with `provider,`.
In `_consolidate`, replace
```python
        api_key = config.get_anthropic_key()
        if not api_key:
            messagebox.showerror("CampaignScribe", "API key missing.")
            return
```
with
```python
        if not llm.provider_ready():
            messagebox.showerror("CampaignScribe", llm.not_ready_message())
            return
        try:
            provider = llm.get_provider()
        except llm.LLMError as e:
            messagebox.showerror("CampaignScribe", str(e))
            return
```
change `self._set_status("Consolidating with Claude…")` to `self._set_status(f"Consolidating with {provider.display_name}…")`, replace `api_key,` in `consolidate_summaries(...)` with `provider,`, and add `model_used=summarizer.model_label(provider),` to the `summarizer.write_docx(...)` call after `campaign_name=campaign,`.

- [ ] **Step 6: `refine_tab.py`**

Import: `from app.core import audio, library, llm, privacy, speaker_id, speakers_io, transcriber`.
Replace lines 199–201 with:
```python
        if not llm.provider_ready():
            messagebox.showerror("CampaignScribe", llm.not_ready_message())
            return
```
In `_worker`, replace `api_key = config.get_anthropic_key()` with `provider = llm.get_provider()` **inside** the existing `try:` (move it to be the first statement after `try:`; the existing `except Exception` already logs and shows `str(e)`). Change `self._set_status("Asking Claude for refinement suggestions…", 0.95)` to `self._set_status(f"Asking {provider.display_name} for refinement suggestions…", 0.95)` and `speaker_id.refine_speakers(all_segments, self.speakers_doc, api_key)` to `speaker_id.refine_speakers(all_segments, self.speakers_doc, provider)`.

- [ ] **Step 7: `edit_profile_window.py`**

Inside `_discover_from_audio`, change the local import to `from app.core import audio, llm, speaker_id, transcriber` and replace
```python
        api_key = config.get_anthropic_key()
        hf = config.get_huggingface_token()
        if not api_key or not hf:
            messagebox.showerror(
                "CampaignScribe",
                "Discover needs an Anthropic API key and a HuggingFace token (Settings ⚙).",
            )
            return
```
with
```python
        hf = config.get_huggingface_token()
        if not llm.provider_ready() or not hf:
            messagebox.showerror(
                "CampaignScribe",
                "Discover needs an AI provider key and a HuggingFace token (Settings ⚙).\n"
                + (llm.not_ready_message() or "HuggingFace token is missing."),
            )
            return
```
In the nested `worker()`, add `provider = llm.get_provider()` as the first statement inside its outer `try:` and change `speaker_id.discover_speakers(segments, api_key)` to `speaker_id.discover_speakers(segments, provider)`.

- [ ] **Step 8: Run the suite**

Run: `.venv\Scripts\python -m pytest tests/gui/test_llm_preflight.py -v` → 3 PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.
Run: `Select-String -Path app\ui\*.py -Pattern "get_anthropic_key|api_key"` → the only remaining hits are in `settings_dialog.py` (Task 8 replaces them).

- [ ] **Step 9: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/ui tests/gui/test_llm_preflight.py
git commit -m "feat(llm): UI workers build the active provider; pre-flight and banner use provider_ready"
```

---

### Task 8: Settings dialog — "AI model" section with Test connection

**Files:**
- Modify: `app/ui/settings_dialog.py` (replace the Anthropic row; add the section; extend `_save`)
- Test: `tests/gui/test_settings_llm.py` (new)

**Interfaces:**
- Consumes: `llm.PRESETS`, `llm.BASE_URLS`, `llm.make_provider`, `llm.LLMError`, `config.save_provider_key/get_provider_key`.
- Produces: `SettingsDialog.llm_provider_var` (display name), `llm_model_var`, `api_var` (key of the selected provider), `llm_base_url_var`, `llm_test_label`, methods `_on_provider_change()`, `_test_connection()`, `_stash_llm_fields()`, `_load_llm_fields()`, attribute `_llm_state: dict[str, dict[str, str]]`, `_llm_current: str`.

- [ ] **Step 1: Write the failing GUI tests**

Create `tests/gui/test_settings_llm.py`:
```python
"""SettingsDialog AI-model section: provider switch, per-provider persistence, Test connection."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
from app.core import llm

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


def _open(root):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root)
    root.update_idletasks()
    return dlg


def _select(dlg, display_name):
    dlg.llm_provider_var.set(display_name)
    dlg._on_provider_change()
    dlg.update_idletasks()


def test_opens_on_saved_provider_with_its_values(root):
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    cfg["llm_model_gemini"] = "gemini-2.5-pro"
    config.save_config(cfg)
    config.save_provider_key("gemini", "g-key")
    dlg = _open(root)
    try:
        assert dlg.llm_provider_var.get() == "Google Gemini"
        assert dlg.llm_model_var.get() == "gemini-2.5-pro"
        assert dlg.api_var.get() == "g-key"
        assert dlg.llm_base_url_row.winfo_manager() == ""  # hidden for non-custom
    finally:
        dlg.destroy()


def test_switching_provider_swaps_fields_and_keeps_edits(root):
    config.save_provider_key("anthropic", "a-key")
    dlg = _open(root)
    try:
        assert dlg.api_var.get() == "a-key"
        dlg.llm_model_var.set("claude-opus-5-5")
        _select(dlg, "OpenRouter")
        assert dlg.api_var.get() == ""
        assert dlg.llm_model_var.get() == llm.PRESETS["openrouter"].default_model
        dlg.api_var.set("or-key")
        _select(dlg, "Custom endpoint")
        assert dlg.llm_base_url_row.winfo_manager() == "grid"
        assert dlg.llm_key_row.winfo_manager() == "grid"  # key optional but still editable
        _select(dlg, "Claude")
        assert dlg.llm_model_var.get() == "claude-opus-5-5"
        assert dlg.api_var.get() == "a-key"
        assert dlg._llm_state["openrouter"]["key"] == "or-key"
    finally:
        dlg.destroy()


def test_save_persists_every_touched_provider_and_strips_base_url(root):
    dlg = _open(root)
    dlg.api_var.set(" a-key \n")
    _select(dlg, "Custom endpoint")
    dlg.llm_model_var.set("llama3")
    dlg.llm_base_url_var.set("  http://localhost:11434/v1/ ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    cfg = config.load_config()
    assert cfg["llm_provider"] == "custom"
    assert cfg["llm_model_custom"] == "llama3"
    assert cfg["llm_base_url_custom"] == "http://localhost:11434/v1"
    assert config.get_provider_key("anthropic") == "a-key"
    assert config.get_provider_key("custom") == ""


def test_blank_model_saves_preset_default(root):
    dlg = _open(root)
    dlg.llm_model_var.set("   ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == "claude-sonnet-5-5"


def test_test_connection_reports_success_and_error(root, monkeypatch):
    class _Good:
        display_name = "Claude"
        model = "claude-sonnet-5-5"

        def complete(self, prompt, max_tokens, json_mode=False):
            return "OK"

    monkeypatch.setattr(llm, "make_provider", lambda *a, **k: _Good())
    import app.ui.settings_dialog as sd

    monkeypatch.setattr(sd.llm, "make_provider", lambda *a, **k: _Good())
    dlg = _open(root)
    try:
        dlg.api_var.set("k")
        dlg._test_connection(_sync=True)
        dlg.update_idletasks()
        assert dlg.llm_test_label.cget("text").startswith("✓ Connected")
        assert "claude-sonnet-5-5" in dlg.llm_test_label.cget("text")

        def _bad(*a, **k):
            raise llm.LLMError("anthropic", "Claude rejected the API key. Check Settings (⚙).", kind="auth")

        monkeypatch.setattr(sd.llm, "make_provider", _bad)
        dlg._test_connection(_sync=True)
        dlg.update_idletasks()
        assert "rejected the API key" in dlg.llm_test_label.cget("text")
    finally:
        dlg.destroy()


def test_test_connection_result_after_destroy_is_ignored(root, monkeypatch):
    dlg = _open(root)
    dlg.destroy()
    root.update_idletasks()
    # Simulate the worker's completion callback arriving after the dialog is gone.
    dlg._report_test_result("✓ Connected (x)")  # must not raise TclError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py -v`
Expected: FAIL (`AttributeError: 'SettingsDialog' object has no attribute 'llm_provider_var'`).

- [ ] **Step 3: Implement the section**

In `app/ui/settings_dialog.py`:

Imports become:
```python
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import llm
```
Update the module docstring to `"""Settings dialog: AI model/provider, HF token, default model, output folder, # speakers."""`.

Replace the block from `ttk.Label(self, text="Anthropic API key:")` through the `row += 1` that follows the Anthropic "Show" checkbutton (the first ~13 lines inside `__init__` after `row = 0`) with:
```python
        row = self._build_llm_section(row, pad)
```
Keep the HuggingFace row and everything after it unchanged.

Add these methods to the class (after `__init__`):
```python
    # ---- AI model section ----
    def _build_llm_section(self, row: int, pad: dict) -> int:
        cfg = config.load_config()
        self._llm_state: dict[str, dict[str, str]] = {}
        self._llm_loaded_keys: dict[str, str] = {}
        for pid, preset in llm.PRESETS.items():
            key = config.get_provider_key(pid)
            self._llm_loaded_keys[pid] = key
            self._llm_state[pid] = {
                "model": cfg.get(f"llm_model_{pid}", "") or preset.default_model,
                "key": key,
                "base_url": cfg.get("llm_base_url_custom", "") if preset.needs_base_url else "",
            }
        self._llm_current = cfg.get("llm_provider", "anthropic")
        if self._llm_current not in llm.PRESETS:
            self._llm_current = "anthropic"
        self._display_to_id = {p.display_name: pid for pid, p in llm.PRESETS.items()}

        ttk.Label(self, text="— AI model —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 0)
        )
        row += 1

        ttk.Label(self, text="Provider:").grid(row=row, column=0, sticky="w", **pad)
        self.llm_provider_var = tk.StringVar(value=llm.PRESETS[self._llm_current].display_name)
        self.llm_provider_combo = ttk.Combobox(
            self,
            textvariable=self.llm_provider_var,
            state="readonly",
            width=28,
            values=[p.display_name for p in llm.PRESETS.values()],
        )
        self.llm_provider_combo.grid(row=row, column=1, sticky="w", **pad)
        self.llm_provider_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_provider_change())
        row += 1

        ttk.Label(self, text="Model:").grid(row=row, column=0, sticky="w", **pad)
        self.llm_model_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.llm_model_var, width=55).grid(row=row, column=1, **pad)
        ttk.Button(self, text="Default", command=self._reset_model).grid(row=row, column=2, **pad)
        row += 1

        self.llm_key_row = ttk.Frame(self)
        self.llm_key_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_key_row, text="API key:").grid(row=0, column=0, sticky="w", **pad)
        self.api_var = tk.StringVar()
        self.api_entry = ttk.Entry(self.llm_key_row, textvariable=self.api_var, width=55, show="•")
        self.api_entry.grid(row=0, column=1, **pad)
        self.api_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.llm_key_row,
            text="Show",
            variable=self.api_show_var,
            command=self._toggle_api_visibility,
        ).grid(row=0, column=2, sticky="w", **pad)
        self.llm_key_row.columnconfigure(1, weight=1)
        row += 1

        self.llm_base_url_row = ttk.Frame(self)
        self.llm_base_url_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_base_url_row, text="Base URL:").grid(row=0, column=0, sticky="w", **pad)
        self.llm_base_url_var = tk.StringVar()
        ttk.Entry(self.llm_base_url_row, textvariable=self.llm_base_url_var, width=55).grid(
            row=0, column=1, **pad
        )
        self.llm_base_url_row.columnconfigure(1, weight=1)
        row += 1

        self.llm_test_btn = ttk.Button(self, text="Test connection", command=self._test_connection)
        self.llm_test_btn.grid(row=row, column=0, sticky="w", **pad)
        self.llm_test_label = ttk.Label(self, text="", wraplength=420, justify="left")
        self.llm_test_label.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        row += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 6)
        )
        row += 1

        self._load_llm_fields()
        return row

    def _stash_llm_fields(self) -> None:
        st = self._llm_state[self._llm_current]
        st["model"] = self.llm_model_var.get()
        st["key"] = self.api_var.get()
        if llm.PRESETS[self._llm_current].needs_base_url:
            st["base_url"] = self.llm_base_url_var.get()

    def _load_llm_fields(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        st = self._llm_state[self._llm_current]
        self.llm_model_var.set(st["model"])
        self.api_var.set(st["key"])
        self.llm_base_url_var.set(st["base_url"])
        if preset.needs_base_url:
            self.llm_base_url_row.grid()
        else:
            self.llm_base_url_row.grid_remove()
        # The key row stays visible for every v1 preset (custom accepts an optional key).
        self.llm_key_row.grid()
        self.llm_test_label.config(text="")

    def _on_provider_change(self) -> None:
        new_id = self._display_to_id.get(self.llm_provider_var.get(), "anthropic")
        if new_id == self._llm_current:
            return
        self._stash_llm_fields()
        self._llm_current = new_id
        self._load_llm_fields()

    def _reset_model(self) -> None:
        self.llm_model_var.set(llm.PRESETS[self._llm_current].default_model)

    def _test_connection(self, _sync: bool = False) -> None:
        self._stash_llm_fields()
        pid = self._llm_current
        st = self._llm_state[pid]
        self.llm_test_label.config(text="Testing…")
        self.llm_test_btn.config(state="disabled")

        def run() -> str:
            try:
                provider = llm.make_provider(
                    pid, model=st["model"], api_key=st["key"].strip(), base_url=st["base_url"]
                )
                provider.complete("Reply with the single word OK.", max_tokens=5)
                return f"✓ Connected ({provider.display_name} · {provider.model})"
            except llm.LLMError as e:
                return f"✗ {e}"
            except Exception as e:  # noqa: BLE001 - surfaced inline, never crashes the dialog
                return f"✗ {type(e).__name__}: {e}"

        if _sync:
            self._report_test_result(run())
            return

        def worker() -> None:
            result = run()
            try:
                self.after(0, lambda: self._report_test_result(result))
            except tk.TclError:
                pass  # dialog already destroyed

        threading.Thread(target=worker, daemon=True).start()

    def _report_test_result(self, text: str) -> None:
        try:
            if not self.winfo_exists():
                return
            self.llm_test_label.config(text=text)
            self.llm_test_btn.config(state="normal")
        except tk.TclError:
            pass
```

In `_save`, replace `config.save_anthropic_key(self.api_var.get().strip())` with:
```python
            self._stash_llm_fields()
            for pid, st in self._llm_state.items():
                key = st["key"].strip()
                if key != self._llm_loaded_keys.get(pid, ""):
                    config.save_provider_key(pid, key)
```
and after `cfg = config.load_config()` add:
```python
            cfg["llm_provider"] = self._llm_current
            for pid, st in self._llm_state.items():
                cfg[f"llm_model_{pid}"] = st["model"].strip() or llm.PRESETS[pid].default_model
            cfg["llm_base_url_custom"] = self._llm_state["custom"]["base_url"].strip().rstrip("/")
```
Keep `_toggle_api_visibility` and `_toggle_hf_visibility` as they are. Change the final `self.api_entry.focus_set()` to `self.llm_provider_combo.focus_set()`.

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py tests/gui/test_settings_discovery.py tests/gui/test_settings_crash_reporting.py -v`
Expected: all PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/ui/settings_dialog.py tests/gui/test_settings_llm.py
git commit -m "feat(llm): Settings AI-model section with per-provider model/key/base URL and Test connection"
```

---

### Task 9: Privacy — PRIVACY.md, provider-aware notes, Privacy dialog links

**Files:**
- Modify: `PRIVACY.md` (two sections)
- Modify: `app/core/privacy.py`
- Modify: `app/ui/transcribe_tab.py:156-160`, `app/ui/summarize_tab.py:173-176`, `app/ui/refine_tab.py:102-105` (note text + `on_settings_changed`)
- Modify: `app/ui/app_window.py` PrivacyDialog links (the `ttk.Button(... "Anthropic Privacy Policy" ...)` block)
- Test: `tests/unit/test_privacy.py:41-44`, `tests/smoke/test_privacy_dialog.py:66-69`, `tests/gui/test_llm_preflight.py` (one new test)

**Interfaces:**
- Consumes: `llm.active_preset().vendor_label`, `llm.PRESETS[*].privacy_url`.
- Produces: `privacy.note_samples(vendor_label) -> str`, `privacy.note_transcript(vendor_label) -> str`; constants `NOTE_SAMPLES`/`NOTE_TRANSCRIPT` remain as the Anthropic defaults.

- [ ] **Step 1: Update the tests first**

`tests/unit/test_privacy.py`, replace `test_inline_note_strings_reference_anthropic_and_help` with:
```python
def test_inline_note_functions_name_vendor_and_help():
    for fn in (privacy.note_samples, privacy.note_transcript):
        note = fn("Google (Gemini)")
        assert "Google (Gemini)" in note
        assert "Privacy & Data" in note
    assert privacy.NOTE_SAMPLES == privacy.note_samples("Anthropic (Claude)")
    assert privacy.NOTE_TRANSCRIPT == privacy.note_transcript("Anthropic (Claude)")


def test_all_provider_privacy_urls_are_https():
    for url in (privacy.ANTHROPIC_PRIVACY_URL, privacy.GEMINI_PRIVACY_URL, privacy.OPENROUTER_PRIVACY_URL):
        assert url.startswith("https://")
```
`tests/smoke/test_privacy_dialog.py`: in `test_privacy_dialog_builds_and_shows_statement` keep the `"Anthropic Claude API"` assertion and add `assert "OpenRouter" in text_widgets[0].get("1.0", "end")`. Replace `test_api_tabs_have_privacy_notes` with:
```python
def test_api_tabs_have_privacy_notes_for_active_provider(app):
    from app import config

    assert app.transcribe_tab._privacy_note.cget("text") == privacy.note_samples("Anthropic (Claude)")
    assert app.refine_tab._privacy_note.cget("text") == privacy.note_samples("Anthropic (Claude)")
    assert app.summarize_tab._privacy_note.cget("text") == privacy.note_transcript("Anthropic (Claude)")

    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    for tab in (app.transcribe_tab, app.refine_tab, app.summarize_tab):
        tab.on_settings_changed()
    app.update_idletasks()
    assert "Google (Gemini)" in app.transcribe_tab._privacy_note.cget("text")
    assert "Google (Gemini)" in app.summarize_tab._privacy_note.cget("text")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_privacy.py tests/smoke/test_privacy_dialog.py -v`
Expected: FAIL (`AttributeError: module 'app.core.privacy' has no attribute 'note_samples'`).

- [ ] **Step 3: `privacy.py`**

Replace the constants block with:
```python
ANTHROPIC_PRIVACY_URL = "https://www.anthropic.com/legal/privacy"
GEMINI_PRIVACY_URL = "https://ai.google.dev/gemini-api/terms"
OPENROUTER_PRIVACY_URL = "https://openrouter.ai/privacy"
PRIVACY_MD_URL = "https://github.com/Imagination-Industries-LLC/CampaignScribe/blob/main/PRIVACY.md"


def note_samples(vendor_label: str) -> str:
    return (
        f"Speaker samples are sent to {vendor_label} for this step. "
        "Learn more: Help → Privacy & Data."
    )


def note_transcript(vendor_label: str) -> str:
    return (
        f"Transcript text is sent to {vendor_label} for this step. "
        "Learn more: Help → Privacy & Data."
    )


# Defaults (the pre-Phase-2 wording) for callers that have no provider context.
NOTE_SAMPLES = note_samples("Anthropic (Claude)")
NOTE_TRANSCRIPT = note_transcript("Anthropic (Claude)")

_FALLBACK = (
    "CampaignScribe sends short transcript snippets and full transcript text to "
    "the AI provider you choose in Settings (Claude by default) to identify speakers "
    "and write summaries. Your audio, database, saved files, and API keys stay on your "
    "computer. No analytics or telemetry by default. See Help → Privacy & Data and "
    "PRIVACY.md for details."
)
```

- [ ] **Step 4: Tabs refresh their note**

`transcribe_tab.py`: change `self._privacy_note = add_privacy_note(body, privacy.NOTE_SAMPLES)` to `self._privacy_note = add_privacy_note(body, privacy.note_samples(llm.active_preset().vendor_label))` and replace the body of `on_settings_changed` (currently `pass`) with:
```python
        self._privacy_note.config(text=privacy.note_samples(llm.active_preset().vendor_label))
```
`refine_tab.py`: same two edits (`note_samples`).
`summarize_tab.py`: same two edits with `note_transcript`.
(`llm` is already imported in all three from Task 7.)

- [ ] **Step 5: Privacy dialog links**

In `app_window.py` `PrivacyDialog.__init__`, replace the single "Anthropic Privacy Policy" button with:
```python
        for label, url in (
            ("Anthropic policy", privacy.ANTHROPIC_PRIVACY_URL),
            ("Gemini terms", privacy.GEMINI_PRIVACY_URL),
            ("OpenRouter policy", privacy.OPENROUTER_PRIVACY_URL),
        ):
            ttk.Button(links, text=label, style=BTN_LINK, command=lambda u=url: open_url(u)).pack(
                side="left", padx=(0, S_3)
            )
```
(Keep the "View PRIVACY.md on GitHub" and "Close" buttons as they are.)

- [ ] **Step 6: `PRIVACY.md`**

Replace the "Stays on your computer" key bullet with:
```
- **Your AI-provider API keys and HuggingFace token** — stored in Windows Credential Manager; each is sent only to its own service to authenticate.
```
Replace the whole "## Sent to the Anthropic Claude API (and why)" section with:
```
## Sent to your chosen AI provider (and why)
CampaignScribe uses one AI provider at a time — chosen in **Settings → AI model** (Claude by default). For every provider the same three things are sent, and nothing else:
- **Transcript excerpts** (speaker samples) — to identify who is speaking (Discover, Transcribe, Refine).
- **Full transcript text** — to write session summaries (Summarize).
- **Your campaign/speaker context** from `speakers.json` — as context for the above.

Where that data goes depends on the provider you pick:
- **Claude (Anthropic Claude API, default)** — Anthropic states that API inputs are not used to train their models (commercial terms); API logs are retained briefly (~7–30 days) for abuse monitoring. https://www.anthropic.com/legal/privacy
- **Google Gemini** — sent to Google's Gemini API under the Gemini API terms (paid-tier data is not used to improve Google's products; check your tier). https://ai.google.dev/gemini-api/terms
- **OpenRouter** — sent to OpenRouter, which **forwards it to the model vendor you selected** (an extra routing hop; that vendor's own policy then applies). https://openrouter.ai/privacy
- **Custom endpoint** — sent to whatever OpenAI-compatible server you configured. If that is a local server (for example Ollama on your own PC), your transcripts stay on your machine.

The in-app notes on the Transcribe, Summarize and Refine screens always name the provider currently in use.
```

- [ ] **Step 7: Run the suite**

Run: `.venv\Scripts\python -m pytest tests/unit/test_privacy.py tests/smoke/test_privacy_dialog.py -v` → PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 8: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add PRIVACY.md app/core/privacy.py app/ui tests/unit/test_privacy.py tests/smoke/test_privacy_dialog.py
git commit -m "feat(llm): provider-aware privacy statement, in-app notes and policy links"
```

---

### Task 10: Packaging, docs and the full gate

**Files:**
- Modify: `requirements.txt`, `setup_venv.bat`, `build.bat`, `CampaignScribe.spec`, `README.md`
- Test: full suite + ruff; `tests/unit/test_packaging_lists.py` (new, tiny)

**Interfaces:** none new.

- [ ] **Step 1: Write the failing packaging test**

Create `tests/unit/test_packaging_lists.py`:
```python
"""The three dependency lists and the PyInstaller spec all know about the new SDKs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_requirements_list_new_sdks():
    req = _read("requirements.txt")
    assert "\ngoogle-genai\n" in req
    assert "\nopenai\n" in req


def test_setup_venv_installs_new_sdks():
    bat = _read("setup_venv.bat")
    assert "google-genai" in bat and "openai" in bat


def test_pyinstaller_hidden_imports_include_new_sdks():
    bat = _read("build.bat")
    spec = _read("CampaignScribe.spec")
    assert "--hidden-import=google.genai" in bat and "--hidden-import=openai" in bat
    assert "'google.genai'" in spec and "'openai'" in spec
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/test_packaging_lists.py -v` → 3 FAIL.

- [ ] **Step 3: Update the lists**

`requirements.txt`: after the `anthropic` line add
```
google-genai
openai
```
`setup_venv.bat` step 1 (`pip install ^` block): add `google-genai ^` and `openai ^` lines directly after `anthropic ^`.
`build.bat`: after `--hidden-import=anthropic ^` add
```
    --hidden-import=google.genai ^
    --hidden-import=openai ^
    --collect-data google.genai ^
```
`CampaignScribe.spec`: `hiddenimports` list gains `'google.genai', 'openai'` after `'anthropic'`; after `datas += collect_data_files('anthropic')` add `datas += collect_data_files('google.genai')`.

`README.md`:
- In "Layout" → the Settings bullet, replace `(API key, HuggingFace token, ...` with `(AI provider, model and API key — Claude, Google Gemini, OpenRouter or a custom OpenAI-compatible endpoint — plus HuggingFace token, ...`.
- In "Prerequisites", replace the Anthropic key bullet with:
```
- An API key for the AI provider you choose in Settings → AI model:
  [Anthropic](https://console.anthropic.com/settings/keys) (default),
  [Google Gemini](https://aistudio.google.com/apikey), or
  [OpenRouter](https://openrouter.ai/keys). A custom OpenAI-compatible
  endpoint (for example a local Ollama server) needs a base URL and model
  instead; a key is optional there.
```
- In "Storage", change `API key + HF token` to `AI-provider API keys + HF token`.
- In "Troubleshooting", change `**Claude 401**` to `**"<provider> rejected the API key"**` and the sentence to "the key saved for that provider in Settings → AI model was rejected; re-paste it and use Test connection."

- [ ] **Step 4: Full gate**

Run, in order, and paste the tails into the PR body later:
```
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -m "not gui" -q
Select-String -Path app\**\*.py,tests\**\*.py,README.md,PRIVACY.md -Pattern "claude_api|CLAUDE_MODEL|get_anthropic_key\(" 
```
Expected: ruff clean; both pytest runs green; the Select-String returns only `app/config.py` (the alias definitions) and `tests/unit/test_config.py` / `tests/unit/test_config_llm.py`.

- [ ] **Step 5: Commit**

```
git add requirements.txt setup_venv.bat build.bat CampaignScribe.spec README.md tests/unit/test_packaging_lists.py
git commit -m "build: bundle google-genai and openai; README documents provider choice"
```

- [ ] **Step 6: Hand back to the controller**

Report: commit list, test counts, and the three manual smoke items the controller runs from `run_dev.bat` before the PR is marked ready (one real transcript summarised through Claude, Gemini and OpenRouter; a wrong key on each shows the provider-named error; Settings → Test connection works for all three). The PR body must include `Roadmap: Imagination-Industries-LLC/CampaignScribe-planning#8`.
