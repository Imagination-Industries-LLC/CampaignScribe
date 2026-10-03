# Local LLM Support & Annotated Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ollama and LM Studio as local, key-free providers with runtime detection, and show Key / Cost / Privacy / Quality badges for every provider choice in Settings.

**Architecture:** A new Tk-free `app/core/llm/local_detect.py` probes the two local runtimes over HTTP with the standard library. `factory.py` gains two local presets, badge fields on `Preset`, a `badges_for()` helper, a per-preset timeout, and local-aware readiness messages; `OpenAICompatProvider` accepts the timeout and a runtime hint for its network error. The Settings "AI model" section gets a badge row, an editable model combobox filled by a Detect button (worker thread + queue polled from the Tk thread), a local caveat line, and stops pinning default model ids on save. PRIVACY.md and README gain the local wording.

**Tech Stack:** Python 3.11, Tkinter/ttk, `urllib` (stdlib) for detection, `openai` SDK (via the existing compat adapter), pytest with `http.server` for detector tests. Windows + PowerShell 5.1; run everything through `.venv\Scripts\python`.

**Spec:** `docs/superpowers/specs/2026-10-03-local-llm-model-picker-design.md` — read it first.

## Global Constraints

- Branch `feature/local-llm-model-picker` off `main` (spec already committed). One PR at the end; Mike merges.
- Every commit: `.venv\Scripts\python -m ruff check .` and `.venv\Scripts\python -m ruff format .` clean first. Single-line commit messages. **No AI attribution, no `Co-Authored-By`.**
- `.venv\Scripts\python -m pytest -q` (full, GUI included) must stay green after every task (318 tests at branch start).
- No change to the ML pins in `requirements.txt`; no new runtime dependencies (detection is stdlib only); `.github/dependabot.yml` untouched.
- UI code never imports an LLM SDK; Settings talks only to `app.core.llm` (which re-exports `local_detect`).
- Preset ids are exactly `ollama` and `lmstudio`; display names `Ollama (local)` and `LM Studio (local)`; base URLs `http://localhost:11434/v1` and `http://localhost:1234/v1`; `default_model=""`, `needs_key=False`, `needs_base_url=False`, `supports_json_mode` True for ollama / False for lmstudio, `timeout_s=600.0`; cloud presets keep `timeout_s=120.0`.
- Badge strings (exact): key `"API key required"` / `"No key needed"` / `"Key optional"`; cost `"$$ per token"` / `"¢ per token"` / `"Varies by model"` / `"Free · local compute"`; privacy `"Stays on your device"` / `f"Sent to {vendor_label}"`; quality `"Frontier"` / `"Strong"` / `"Varies by model"` / `"Good"` / `"Basic"`. Local quality: parameter size `>= 12B` → `"Good"`, else (or unknown) `"Basic"`.
- Readiness never touches the network. Messages (exact): local preset with blank model → `f"Pick an {display_name} model in Settings (⚙): start {runtime_name} and press Detect."`; adapter network error for a local preset → `f"Could not reach {display_name} ({detail}) — is {runtime_name} running?"` where `runtime_name` is `Ollama` / `LM Studio`.
- No references to the predecessor product name. Every subprocess (none expected) uses `CREATE_NO_WINDOW`.

## Review Focus

Inputs the spec implies but did not spell out; each has a pinned test in the owning task:

1. Ollama running with **zero models pulled** must say so ("0 models found — run `ollama pull <model>`") rather than show an empty combobox silently. → Task 4 `test_detect_with_no_models_explains_pull`.
2. An Ollama tags entry **without `details`** (older runtimes) must still list the model, with Quality `Basic`. → Task 1 `test_ollama_entry_without_details_is_listed_as_basic`.
3. Parameter sizes come in many spellings (`"14.8B"`, `"7B"`, `"8.0B"`, `"1.5B"`, `"unknown"`, `""`); the quality rule must not crash or misgrade. → Task 1 `test_quality_label_table`.
4. The user **switches provider while Detect is running**: the late result must land in the Ollama state, not overwrite the now-selected provider's model field. → Task 4 `test_detect_result_for_other_provider_does_not_touch_current_fields`.
5. The dialog is **destroyed while Detect is running**: the queue poll must stop quietly, no `TclError`. → Task 4 `test_detect_poll_after_destroy_is_quiet`.

---

### Task 1: `local_detect.py` — probe Ollama / LM Studio, list models, quality rule

**Files:**
- Create: `app/core/llm/local_detect.py`
- Modify: `app/core/llm/__init__.py` (re-export the module)
- Test: `tests/unit/test_local_detect.py`

**Interfaces:**
- Produces: `RUNTIMES = {"ollama": "http://localhost:11434/v1", "lmstudio": "http://localhost:1234/v1"}`, `RUNTIME_NAMES = {"ollama": "Ollama", "lmstudio": "LM Studio"}`, `LocalModel(model_id: str, parameter_size: str = "")`, `DetectResult(runtime_id: str, running: bool, models: list[LocalModel], error: str)`, `detect(runtime_id, *, base_url=None, timeout_s=1.5) -> DetectResult` (never raises except `ValueError` for an unknown runtime id), `quality_label(parameter_size: str) -> str`, `QUALITY_GOOD_MIN_B = 12.0`. Importable as `from app.core.llm import local_detect`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_local_detect.py`:
```python
"""local_detect: probe fake Ollama / LM Studio servers, handle failures, grade quality."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.llm import local_detect


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, bytes]] = {}

    def do_GET(self):  # noqa: N802 - http.server API
        status, body = self.routes.get(self.path, (404, b"{}"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture
def server():
    """Yields (base_url, routes) for a local HTTP server; set routes before calling detect."""
    _Handler.routes = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", _Handler.routes
    finally:
        srv.shutdown()
        srv.server_close()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_ollama_lists_models_with_sizes(server):
    base, routes = server
    routes["/api/tags"] = (
        200,
        json.dumps(
            {
                "models": [
                    {"name": "qwen2.5:14b", "details": {"parameter_size": "14.8B"}},
                    {"name": "llama3.1:8b", "details": {"parameter_size": "8.0B"}},
                ]
            }
        ).encode(),
    )
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running and r.error == ""
    assert [m.model_id for m in r.models] == ["qwen2.5:14b", "llama3.1:8b"]
    assert r.models[0].parameter_size == "14.8B"


def test_ollama_entry_without_details_is_listed_as_basic(server):
    base, routes = server
    routes["/api/tags"] = (200, json.dumps({"models": [{"name": "tiny:latest"}]}).encode())
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running
    assert r.models == [local_detect.LocalModel("tiny:latest", "")]
    assert local_detect.quality_label(r.models[0].parameter_size) == "Basic"


def test_lmstudio_lists_ids(server):
    base, routes = server
    routes["/v1/models"] = (
        200,
        json.dumps({"data": [{"id": "qwen2.5-14b-instruct"}, {"id": "phi-4"}]}).encode(),
    )
    r = local_detect.detect("lmstudio", base_url=f"{base}/v1")
    assert r.running
    assert [m.model_id for m in r.models] == ["qwen2.5-14b-instruct", "phi-4"]
    assert all(m.parameter_size == "" for m in r.models)


def test_connection_refused_is_not_running():
    port = _free_port()
    r = local_detect.detect("ollama", base_url=f"http://127.0.0.1:{port}/v1", timeout_s=0.5)
    assert r.running is False
    assert r.models == []
    assert r.error  # names the failure, e.g. URLError: ... refused


def test_malformed_json_is_not_running(server):
    base, routes = server
    routes["/api/tags"] = (200, b"<html>not json</html>")
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running is False and "unexpected response" in r.error


def test_unexpected_shape_is_not_running(server):
    base, routes = server
    routes["/v1/models"] = (200, json.dumps([1, 2, 3]).encode())
    r = local_detect.detect("lmstudio", base_url=f"{base}/v1")
    assert r.running is False and "unexpected response" in r.error


def test_http_error_is_not_running(server):
    base, routes = server
    routes["/api/tags"] = (500, b"{}")
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running is False and "HTTPError" in r.error


def test_unknown_runtime_raises():
    with pytest.raises(ValueError):
        local_detect.detect("banana")


def test_default_base_urls():
    assert local_detect.RUNTIMES == {
        "ollama": "http://localhost:11434/v1",
        "lmstudio": "http://localhost:1234/v1",
    }
    assert local_detect.RUNTIME_NAMES == {"ollama": "Ollama", "lmstudio": "LM Studio"}


@pytest.mark.parametrize(
    "size, label",
    [
        ("", "Basic"),
        ("unknown", "Basic"),
        ("1.5B", "Basic"),
        ("7B", "Basic"),
        ("8.0B", "Basic"),
        ("11.9B", "Basic"),
        ("12B", "Good"),
        ("14.8B", "Good"),
        ("70B", "Good"),
        ("  32b ", "Good"),
    ],
)
def test_quality_label_table(size, label):
    assert local_detect.quality_label(size) == label
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_local_detect.py -v`
Expected: FAIL with `ImportError: cannot import name 'local_detect' from 'app.core.llm'`

- [ ] **Step 3: Implement the module**

Create `app/core/llm/local_detect.py`:
```python
"""Probe local OpenAI-compatible runtimes (Ollama, LM Studio) and list their models.

Pure urllib with a short timeout; a stopped runtime is a result, not an
exception. Tk-free; no SDK import. Settings runs this on a worker thread.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

RUNTIMES: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}
RUNTIME_NAMES: dict[str, str] = {"ollama": "Ollama", "lmstudio": "LM Studio"}

_DEFAULT_TIMEOUT_S = 1.5
QUALITY_GOOD_MIN_B = 12.0
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[bB]")


@dataclass(frozen=True)
class LocalModel:
    model_id: str
    parameter_size: str = ""  # "14.8B" when the runtime reports it, else ""


@dataclass(frozen=True)
class DetectResult:
    runtime_id: str
    running: bool
    models: list[LocalModel] = field(default_factory=list)
    error: str = ""  # "" when running; otherwise a one-line reason


def quality_label(parameter_size: str) -> str:
    """'Good' at or above QUALITY_GOOD_MIN_B billion parameters, else 'Basic'."""
    m = _SIZE_RE.match(parameter_size or "")
    if not m:
        return "Basic"
    return "Good" if float(m.group(1)) >= QUALITY_GOOD_MIN_B else "Basic"


def _get_json(url: str, timeout_s: float):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - localhost only
        return json.loads(resp.read().decode("utf-8"))


def detect(
    runtime_id: str, *, base_url: str | None = None, timeout_s: float = _DEFAULT_TIMEOUT_S
) -> DetectResult:
    """Probe one runtime. Never raises for network/format problems."""
    if runtime_id not in RUNTIMES:
        raise ValueError(f"unknown local runtime: {runtime_id!r}")
    base = (base_url or RUNTIMES[runtime_id]).rstrip("/")
    try:
        if runtime_id == "ollama":
            root = base[: -len("/v1")] if base.endswith("/v1") else base
            data = _get_json(f"{root}/api/tags", timeout_s)
            models = [
                LocalModel(
                    str(m.get("name") or m.get("model") or ""),
                    str((m.get("details") or {}).get("parameter_size") or ""),
                )
                for m in data["models"]
            ]
        else:
            data = _get_json(f"{base}/models", timeout_s)
            models = [LocalModel(str(m.get("id") or "")) for m in data["data"]]
        models = [m for m in models if m.model_id]
        return DetectResult(runtime_id, True, models)
    except urllib.error.HTTPError as e:
        return DetectResult(runtime_id, False, [], f"HTTPError: {e.code}")
    except (urllib.error.URLError, OSError) as e:  # refused, timeout, DNS
        reason = getattr(e, "reason", None) or e
        return DetectResult(runtime_id, False, [], f"{type(e).__name__}: {reason}")
    except (ValueError, KeyError, AttributeError, TypeError) as e:  # bad JSON / wrong shape
        return DetectResult(runtime_id, False, [], f"unexpected response: {type(e).__name__}: {e}")
```

In `app/core/llm/__init__.py` add `from app.core.llm import local_detect` after the base import and `"local_detect"` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_local_detect.py -v`
Expected: 19 PASS (9 named tests + 10 parametrized cases). If `test_http_error_is_not_running` fails because `HTTPError` is caught by the `URLError` clause first, keep the `HTTPError` clause above it (it already is in the code above — `HTTPError` subclasses `URLError`).

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/local_detect.py app/core/llm/__init__.py tests/unit/test_local_detect.py
git commit -m "feat(llm): local_detect probes Ollama/LM Studio and grades model quality by size"
```

---

### Task 2: `OpenAICompatProvider` — per-preset timeout and local runtime hint

**Files:**
- Modify: `app/core/llm/openai_compat_provider.py`
- Test: `tests/unit/test_llm_openai_compat.py`

**Interfaces:**
- Consumes: Task 1 `local_detect.RUNTIME_NAMES`.
- Produces: `OpenAICompatProvider(api_key, model, base_url, *, provider_id, display_name, supports_json_mode, timeout_s: float = 120.0, local_runtime: str = "")`; network errors for a local runtime read `f"Could not reach {display_name} ({detail}) — is {RUNTIME_NAMES[local_runtime]} running?"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_openai_compat.py`:
```python
def test_timeout_s_reaches_client(fake_openai):
    _make(fake_openai, timeout_s=600.0)
    assert fake_openai.captured["timeout"] == 600.0


def test_local_runtime_network_error_asks_if_runtime_is_running(fake_openai):
    import openai

    req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    fake_openai(openai.APIConnectionError(request=req))
    p = _make(
        fake_openai,
        api_key="",
        base_url="http://localhost:11434/v1",
        provider_id="ollama",
        display_name="Ollama (local)",
        local_runtime="ollama",
    )
    with pytest.raises(base.LLMError) as ei:
        p.complete("x", max_tokens=5)
    assert ei.value.kind == "network"
    assert str(ei.value) == "Could not reach Ollama (local) (APIConnectionError) — is Ollama running?"


def test_cloud_network_error_unchanged(fake_openai):
    import openai

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    fake_openai(openai.APIConnectionError(request=req))
    with pytest.raises(base.LLMError) as ei:
        _make(fake_openai).complete("x", max_tokens=5)
    assert str(ei.value) == "Could not reach OpenRouter (APIConnectionError)."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_openai_compat.py -v`
Expected: the two new tests that pass `timeout_s`/`local_runtime` FAIL with `TypeError: unexpected keyword argument`; `test_cloud_network_error_unchanged` PASSES already.

- [ ] **Step 3: Implement**

In `app/core/llm/openai_compat_provider.py`:
- add `from app.core.llm.local_detect import RUNTIME_NAMES` to the imports;
- extend the constructor signature with `timeout_s: float = _TIMEOUT_TOTAL, local_runtime: str = ""` (after `supports_json_mode`), store `self._local_runtime = local_runtime`, and pass `timeout=timeout_s` to `openai.OpenAI(...)` instead of `_TIMEOUT_TOTAL`;
- replace the `except o.APIConnectionError as e:` clause body with:
```python
        except o.APIConnectionError as e:
            if self._local_runtime:
                raise LLMError(
                    self.provider_id,
                    f"Could not reach {self.display_name} ({type(e).__name__}) — "
                    f"is {RUNTIME_NAMES.get(self._local_runtime, self.display_name)} running?",
                    kind="network",
                ) from e
            raise network_error(self.provider_id, self.display_name, type(e).__name__) from e
```
- update the module docstring's second sentence to "Serves OpenRouter, the Ollama / LM Studio local presets, and custom endpoints: same code, different base_url, model and timeout."

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_openai_compat.py -v` → all PASS (13).
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/openai_compat_provider.py tests/unit/test_llm_openai_compat.py
git commit -m "feat(llm): OpenAICompatProvider takes timeout_s and names the local runtime in network errors"
```

---

### Task 3: Presets, badges, readiness and config for the two local runtimes

**Files:**
- Modify: `app/core/llm/factory.py` (Preset fields, PRESETS, BASE_URLS, `badges_for`, `make_provider`, `not_ready_message`)
- Modify: `app/core/llm/__init__.py` (export `badges_for`)
- Modify: `app/config.py:37-44` (two defaults)
- Test: `tests/unit/test_llm_factory.py` (update one test, add six), `tests/unit/test_config_llm.py` (extend one test)

**Interfaces:**
- Consumes: Task 1 `local_detect.RUNTIMES`, `RUNTIME_NAMES`, `quality_label`; Task 2 `OpenAICompatProvider(..., timeout_s=, local_runtime=)`.
- Produces: `Preset` with new fields `key_label: str`, `cost_label: str`, `quality_label: str`, `timeout_s: float`, `local_runtime: str` (all after the existing eight, with defaults so positional construction of the old fields still works); `PRESETS` order `anthropic, gemini, openrouter, ollama, lmstudio, custom`; `BASE_URLS` gains `ollama`/`lmstudio`; `badges_for(preset, model_id="", parameter_size="") -> list[str]` (Key, Cost, Privacy, Quality); `make_provider` passes `timeout_s=preset.timeout_s` and `local_runtime=preset.local_runtime` to `OpenAICompatProvider` (keywords added in Task 2).

- [ ] **Step 1: Update and add the factory tests**

In `tests/unit/test_llm_factory.py`, change the first line of `test_presets_order_and_shape` to:
```python
    assert list(llm.PRESETS) == ["anthropic", "gemini", "openrouter", "ollama", "lmstudio", "custom"]
```
and append these tests to the file:
```python
def test_local_presets_shape():
    o = llm.PRESETS["ollama"]
    assert o.display_name == "Ollama (local)" and o.local_runtime == "ollama"
    assert o.default_model == "" and not o.needs_key and not o.needs_base_url
    assert o.supports_json_mode is True and o.timeout_s == 600.0
    assert o.vendor_label == "your own computer (Ollama)" and o.privacy_url == ""
    s = llm.PRESETS["lmstudio"]
    assert s.display_name == "LM Studio (local)" and s.local_runtime == "lmstudio"
    assert s.supports_json_mode is False and s.timeout_s == 600.0
    assert llm.BASE_URLS["ollama"] == "http://localhost:11434/v1"
    assert llm.BASE_URLS["lmstudio"] == "http://localhost:1234/v1"
    for pid in ("anthropic", "gemini", "openrouter", "custom"):
        assert llm.PRESETS[pid].local_runtime == "" and llm.PRESETS[pid].timeout_s == 120.0


def test_make_provider_local_preset_builds_compat_provider_without_key():
    p = llm.make_provider("ollama", model="qwen2.5:14b", api_key="")
    assert p.provider_id == "ollama" and p.base_url == "http://localhost:11434/v1"
    assert p.model == "qwen2.5:14b" and p.supports_json_mode is True
    assert p._client.kwargs["timeout"] == 600.0
    assert p._client.kwargs["api_key"] == "sk-none"
    s = llm.make_provider("lmstudio", model="phi-4", api_key="")
    assert s.base_url == "http://localhost:1234/v1" and s.supports_json_mode is False


def test_make_provider_local_preset_blank_model_is_missing_key():
    with pytest.raises(llm.LLMError) as ei:
        llm.make_provider("ollama", model="  ", api_key="")
    assert ei.value.kind == "missing_key"
    assert str(ei.value) == (
        "Pick an Ollama (local) model in Settings (⚙): start Ollama and press Detect."
    )


@pytest.mark.parametrize(
    "pid, model, size, expected",
    [
        ("anthropic", "claude-sonnet-5-5", "", ["API key required", "$$ per token", "Sent to Anthropic (Claude)", "Frontier"]),
        ("gemini", "gemini-2.5-flash", "", ["API key required", "¢ per token", "Sent to Google (Gemini)", "Strong"]),
        ("openrouter", "x", "", ["API key required", "Varies by model", "Sent to OpenRouter (which forwards it to the model vendor you chose)", "Varies by model"]),
        ("custom", "x", "", ["Key optional", "Varies by model", "Sent to the custom endpoint you configured", "Varies by model"]),
        ("ollama", "qwen2.5:14b", "14.8B", ["No key needed", "Free · local compute", "Stays on your device", "Good"]),
        ("ollama", "llama3.1:8b", "8.0B", ["No key needed", "Free · local compute", "Stays on your device", "Basic"]),
        ("lmstudio", "phi-4", "", ["No key needed", "Free · local compute", "Stays on your device", "Basic"]),
    ],
)
def test_badges_for_table(pid, model, size, expected):
    assert llm.badges_for(llm.PRESETS[pid], model, size) == expected


def test_not_ready_message_local_without_model_then_ready():
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    config.save_config(cfg)
    assert llm.not_ready_message() == (
        "Pick an Ollama (local) model in Settings (⚙): start Ollama and press Detect."
    )
    assert llm.provider_ready() is False
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    assert llm.not_ready_message() == ""
    assert llm.provider_ready() is True
    assert llm.get_provider().model == "qwen2.5:14b"


def test_lmstudio_not_ready_names_lm_studio():
    cfg = config.load_config()
    cfg["llm_provider"] = "lmstudio"
    config.save_config(cfg)
    assert llm.not_ready_message() == (
        "Pick an LM Studio (local) model in Settings (⚙): start LM Studio and press Detect."
    )
```
In `tests/unit/test_config_llm.py::test_new_llm_defaults_merge_into_old_config_json` append:
```python
    assert cfg["llm_model_ollama"] == ""
    assert cfg["llm_model_lmstudio"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_factory.py tests/unit/test_config_llm.py -v`
Expected: the order test and the six new tests FAIL (`AttributeError: ... has no attribute 'badges_for'`, `KeyError: 'ollama'`, assertion on the order list); the rest PASS.

- [ ] **Step 3: Config defaults**

In `app/config.py` `DEFAULT_CONFIG`, after `"llm_model_openrouter": ...` add:
```python
    "llm_model_ollama": "",  # chosen via Settings → Detect; blank = not picked yet
    "llm_model_lmstudio": "",
```

- [ ] **Step 4: Factory changes**

Replace the `Preset` dataclass, `PRESETS`, and `BASE_URLS` in `app/core/llm/factory.py` with:
```python
from app.core.llm.local_detect import RUNTIME_NAMES, RUNTIMES, quality_label


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
    key_label: str = "API key required"
    cost_label: str = "Varies by model"
    quality_label: str = "Varies by model"  # local presets: derived per model instead
    timeout_s: float = 120.0
    local_runtime: str = ""  # "" for cloud/custom; "ollama" | "lmstudio" for local presets


PRESETS: dict[str, Preset] = {
    "anthropic": Preset(
        "anthropic", "Claude", "Anthropic (Claude)", "claude-sonnet-5-5",
        True, False, False, "https://www.anthropic.com/legal/privacy",
        cost_label="$$ per token", quality_label="Frontier",
    ),
    "gemini": Preset(
        "gemini", "Google Gemini", "Google (Gemini)", "gemini-2.5-flash",
        True, False, True, "https://ai.google.dev/gemini-api/terms",
        cost_label="¢ per token", quality_label="Strong",
    ),
    "openrouter": Preset(
        "openrouter", "OpenRouter",
        "OpenRouter (which forwards it to the model vendor you chose)",
        "anthropic/claude-sonnet-4.5", True, False, True, "https://openrouter.ai/privacy",
    ),
    "ollama": Preset(
        "ollama", "Ollama (local)", "your own computer (Ollama)", "",
        False, False, True, "",
        key_label="No key needed", cost_label="Free · local compute", quality_label="",
        timeout_s=600.0, local_runtime="ollama",
    ),
    "lmstudio": Preset(
        "lmstudio", "LM Studio (local)", "your own computer (LM Studio)", "",
        False, False, False, "",
        key_label="No key needed", cost_label="Free · local compute", quality_label="",
        timeout_s=600.0, local_runtime="lmstudio",
    ),
    "custom": Preset(
        "custom", "Custom endpoint", "the custom endpoint you configured", "",
        False, True, False, "",
        key_label="Key optional",
    ),
}

BASE_URLS = {"openrouter": "https://openrouter.ai/api/v1", **RUNTIMES}


def badges_for(preset: Preset, model_id: str = "", parameter_size: str = "") -> list[str]:
    """[Key, Cost, Privacy, Quality] for the Settings badge row."""
    if preset.local_runtime:
        privacy = "Stays on your device"
        quality = quality_label(parameter_size)
    else:
        privacy = f"Sent to {preset.vendor_label}"
        quality = preset.quality_label
    return [preset.key_label, preset.cost_label, privacy, quality]


def _local_pick_message(preset: Preset) -> str:
    return (
        f"Pick an {preset.display_name} model in Settings (⚙): "
        f"start {RUNTIME_NAMES[preset.local_runtime]} and press Detect."
    )
```
(ruff will reflow the long `Preset(...)` literals; accept its formatting.)

In `make_provider`, after the `needs_key` check and the `model = ...` line, add:
```python
    if preset.local_runtime and not model:
        raise LLMError(provider_id, _local_pick_message(preset), kind="missing_key")
```
and change the `OpenAICompatProvider(...)` call to pass two more keywords:
```python
        timeout_s=preset.timeout_s,
        local_runtime=preset.local_runtime,
```

In `not_ready_message`, before the `if preset.needs_key ...` line add:
```python
    if preset.local_runtime:
        model = (c.get(f"llm_model_{preset.provider_id}", "") or "").strip()
        if not model:
            return _local_pick_message(preset)
```
Add `"badges_for"` to `factory.__all__`, and in `app/core/llm/__init__.py` import and export `badges_for` alongside the other factory names.

- [ ] **Step 5: Run the tests and the whole suite**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_factory.py tests/unit/test_config_llm.py -v` → all PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS. (The Settings GUI tests still pass: the dropdown just has two more entries.)

- [ ] **Step 6: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/factory.py app/core/llm/__init__.py app/config.py tests/unit/test_llm_factory.py tests/unit/test_config_llm.py
git commit -m "feat(llm): Ollama and LM Studio presets, badge table, local readiness message, per-preset timeout"
```

---

### Task 4: Settings — badge row, model combobox, Detect, local caveat, save-blank-when-default

**Files:**
- Modify: `app/ui/settings_dialog.py` (`_build_llm_section`, `_stash_llm_fields`, `_load_llm_fields`, `_on_provider_change`, `_save`; new `_refresh_badges`, `_run_detect`, `_poll_detect`, `_apply_detect_result`)
- Test: `tests/gui/test_settings_llm.py` (one test rewritten, seven added)

**Interfaces:**
- Consumes: `llm.PRESETS`, `llm.badges_for`, `llm.local_detect.detect`, `llm.local_detect.DetectResult`/`LocalModel`, `llm.local_detect.RUNTIME_NAMES`.
- Produces: attributes `llm_badge_label` (ttk.Label), `llm_model_combo` (ttk.Combobox, editable), `llm_detect_btn` (ttk.Button), `llm_local_label` (ttk.Label caveat), `_llm_state[pid]["detected"]: list[LocalModel]`, `_detect_queue: queue.Queue`; methods `_refresh_badges()`, `_run_detect(_sync: bool = False)`, `_poll_detect()`, `_apply_detect_result(result)`.

- [ ] **Step 1: Write the failing GUI tests**

In `tests/gui/test_settings_llm.py`, add `from app.core.llm import local_detect` to the imports, **replace** `test_blank_model_saves_preset_default` with:
```python
def test_model_equal_to_default_saves_blank_and_blank_saves_blank(root):
    dlg = _open(root)
    assert dlg.llm_model_var.get() == "claude-sonnet-5-5"  # field shows the default
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == ""  # not pinned
    dlg = _open(root)
    dlg.llm_model_var.set("   ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == ""


def test_custom_model_id_still_saved(root):
    dlg = _open(root)
    dlg.llm_model_var.set("claude-opus-5-5")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == "claude-opus-5-5"
```
and append:
```python
def _scripted_detect(monkeypatch, result_by_runtime):
    calls = []

    def _detect(runtime_id, *, base_url=None, timeout_s=1.5):
        calls.append(runtime_id)
        return result_by_runtime[runtime_id]

    import app.ui.settings_dialog as sd

    monkeypatch.setattr(sd.local_detect, "detect", _detect)
    return calls


_OLLAMA_OK = local_detect.DetectResult(
    "ollama",
    True,
    [local_detect.LocalModel("qwen2.5:14b", "14.8B"), local_detect.LocalModel("llama3.1:8b", "8.0B")],
)
_OLLAMA_DOWN = local_detect.DetectResult("ollama", False, [], "URLError: [WinError 10061] refused")
_OLLAMA_EMPTY = local_detect.DetectResult("ollama", True, [])


def test_badge_row_for_cloud_and_local(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        assert dlg.llm_badge_label.cget("text") == (
            "API key required · $$ per token · Sent to Anthropic (Claude) · Frontier"
        )
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert dlg.llm_badge_label.cget("text") == (
            "No key needed · Free · local compute · Stays on your device · Good"
        )
        dlg.llm_model_var.set("llama3.1:8b")
        dlg._refresh_badges()
        assert dlg.llm_badge_label.cget("text").endswith("· Basic")
    finally:
        dlg.destroy()


def test_local_preset_hides_key_and_url_rows_and_shows_detect(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        assert dlg.llm_detect_btn.winfo_manager() == ""
        _select(dlg, "Ollama (local)")
        assert dlg.llm_key_row.winfo_manager() == ""
        assert dlg.llm_base_url_row.winfo_manager() == ""
        assert dlg.llm_detect_btn.winfo_manager() == "pack"
        _select(dlg, "Claude")
        assert dlg.llm_key_row.winfo_manager() == "grid"
        assert dlg.llm_detect_btn.winfo_manager() == ""
    finally:
        dlg.destroy()


def test_detect_fills_combobox_and_selects_first_when_blank(root, monkeypatch):
    calls = _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert calls and all(c == "ollama" for c in calls)  # auto-run on select + explicit run
        assert list(dlg.llm_model_combo.cget("values")) == ["qwen2.5:14b", "llama3.1:8b"]
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
        assert "2 models found" in dlg.llm_local_label.cget("text")
        assert "speaker-ID JSON" in dlg.llm_local_label.cget("text")
        try:
            dlg._save()
        except tk.TclError:
            pass
        cfg = config.load_config()
        assert cfg["llm_provider"] == "ollama" and cfg["llm_model_ollama"] == "qwen2.5:14b"
    finally:
        try:
            dlg.destroy()
        except tk.TclError:
            pass


def test_detect_runtime_down_shows_start_hint(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_DOWN})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        text = dlg.llm_local_label.cget("text")
        assert text.startswith("Ollama (local) not running — start it, then press Detect.")
        assert "10061" in text
        assert dlg.llm_model_var.get() == ""
        assert str(dlg.llm_detect_btn.cget("state")) == "normal"
    finally:
        dlg.destroy()


def test_detect_with_no_models_explains_pull(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_EMPTY})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert dlg.llm_local_label.cget("text") == (
            "0 models found — run `ollama pull <model>` (e.g. qwen2.5:14b), then press Detect."
        )
        assert list(dlg.llm_model_combo.cget("values")) == []
    finally:
        dlg.destroy()


def test_detect_result_for_other_provider_does_not_touch_current_fields(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_DOWN})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        _select(dlg, "Claude")  # user moved on before a (late) Ollama result arrives
        dlg.llm_model_var.set("claude-opus-5-5")
        dlg._apply_detect_result(_OLLAMA_OK)
        assert dlg.llm_model_var.get() == "claude-opus-5-5"
        assert dlg._llm_state["ollama"]["detected"] == _OLLAMA_OK.models
        assert dlg._llm_state["ollama"]["model"] == "qwen2.5:14b"
        _select(dlg, "Ollama (local)")
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
        assert list(dlg.llm_model_combo.cget("values")) == ["qwen2.5:14b", "llama3.1:8b"]
    finally:
        dlg.destroy()


def test_detect_threaded_path_applies_via_queue(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")  # auto-runs the threaded detect
        for _ in range(100):
            dlg.update()
            if dlg.llm_model_var.get():
                break
            threading.Event().wait(0.02)
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
    finally:
        dlg.destroy()


def test_detect_poll_after_destroy_is_quiet(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    _select(dlg, "Ollama (local)")
    dlg.destroy()
    root.update()
    dlg._poll_detect()  # must not raise
    dlg._apply_detect_result(_OLLAMA_OK)  # must not raise
```
Add `import threading` to the test module imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py -v`
Expected: the new tests FAIL (`AttributeError: 'SettingsDialog' object has no attribute 'llm_badge_label'` / `_run_detect`); `test_model_equal_to_default_saves_blank_and_blank_saves_blank` FAILS on the first assertion (config still pins `claude-sonnet-5-5`).

- [ ] **Step 3: Implement**

In `app/ui/settings_dialog.py`:

Imports: add `import queue` and change the llm import to `from app.core import llm` plus `from app.core.llm import local_detect` (the test patches `sd.local_detect.detect`).

In `_build_llm_section`, in the state-seeding loop add `"detected": []` and `"detected_once": False` entries to each `self._llm_state[pid]` dict, and `self._detect_queue: queue.Queue = queue.Queue()` after the loop.

After the Provider row (`row += 1`) insert the badge row:
```python
        self.llm_badge_label = ttk.Label(self, text="", wraplength=520, justify="left")
        self.llm_badge_label.grid(row=row, column=1, columnspan=2, sticky="w", padx=10, pady=(0, 2))
        row += 1
```
Replace the Model row (`ttk.Label(... "Model:")` through its `row += 1`) with:
```python
        ttk.Label(self, text="Model:").grid(row=row, column=0, sticky="w", **pad)
        self.llm_model_var = tk.StringVar()
        self.llm_model_combo = ttk.Combobox(
            self, textvariable=self.llm_model_var, width=52, state="normal", values=[]
        )
        self.llm_model_combo.grid(row=row, column=1, **pad)
        self.llm_model_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_badges())
        self.llm_model_combo.bind("<KeyRelease>", lambda _e: self._refresh_badges())
        model_btns = ttk.Frame(self)
        model_btns.grid(row=row, column=2, sticky="w", **pad)
        ttk.Button(model_btns, text="Default", command=self._reset_model).pack(side="left")
        self.llm_detect_btn = ttk.Button(model_btns, text="Detect", command=self._run_detect)
        # packed/unpacked by _load_llm_fields
        row += 1

        self.llm_local_label = ttk.Label(self, text="", wraplength=520, justify="left")
        self.llm_local_label.grid(row=row, column=1, columnspan=2, sticky="w", padx=10, pady=(0, 4))
        row += 1
```
Replace `_stash_llm_fields`, `_load_llm_fields` and `_on_provider_change` with:
```python
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
        self.llm_model_combo.config(values=[m.model_id for m in st["detected"]])
        self.api_var.set(st["key"])
        self.llm_base_url_var.set(st["base_url"])
        if preset.needs_base_url:
            self.llm_base_url_row.grid()
        else:
            self.llm_base_url_row.grid_remove()
        if preset.needs_key or preset.provider_id == "custom":
            self.llm_key_row.grid()
        else:
            self.llm_key_row.grid_remove()
        if preset.local_runtime:
            self.llm_detect_btn.pack(side="left", padx=(6, 0))
        else:
            self.llm_detect_btn.pack_forget()
            self.llm_local_label.config(text="")
        self.llm_test_label.config(text="")
        self._refresh_badges()
        if preset.local_runtime and not st["detected_once"]:
            self._run_detect()

    def _on_provider_change(self) -> None:
        new_id = self._display_to_id.get(self.llm_provider_var.get(), "anthropic")
        if new_id == self._llm_current:
            return
        self._stash_llm_fields()
        self._llm_current = new_id
        self._load_llm_fields()

    def _refresh_badges(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        model = self.llm_model_var.get().strip()
        size = ""
        for m in self._llm_state[self._llm_current]["detected"]:
            if m.model_id == model:
                size = m.parameter_size
                break
        self.llm_badge_label.config(text=" · ".join(llm.badges_for(preset, model, size)))

    # ---- local runtime detection ----
    def _run_detect(self, _sync: bool = False) -> None:
        pid = self._llm_current
        preset = llm.PRESETS[pid]
        if not preset.local_runtime:
            return
        self._llm_state[pid]["detected_once"] = True
        self.llm_local_label.config(text=f"Looking for {preset.display_name}…")
        self.llm_detect_btn.config(state="disabled")
        if _sync:
            self._apply_detect_result(local_detect.detect(preset.local_runtime))
            return

        def worker() -> None:
            self._detect_queue.put(local_detect.detect(preset.local_runtime))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_detect)

    def _poll_detect(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            result = self._detect_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_detect)
            return
        self._apply_detect_result(result)

    def _apply_detect_result(self, result) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        pid = result.runtime_id  # preset ids equal runtime ids for the two local presets
        preset = llm.PRESETS[pid]
        st = self._llm_state[pid]
        st["detected"] = list(result.models)
        if result.running and result.models and not st["model"].strip():
            st["model"] = result.models[0].model_id
        if not result.running:
            text = (
                f"{preset.display_name} not running — start it, then press Detect. "
                f"({result.error})"
            )
        elif not result.models:
            text = (
                "0 models found — run `ollama pull <model>` (e.g. qwen2.5:14b), then press Detect."
                if pid == "ollama"
                else "0 models found — load a model in LM Studio, then press Detect."
            )
        else:
            text = (
                f"{len(result.models)} models found. Small models (< 12B) may struggle with "
                "the strict speaker-ID JSON; summaries are fine."
            )
        if pid == self._llm_current:
            self.llm_model_combo.config(values=[m.model_id for m in st["detected"]])
            if not self.llm_model_var.get().strip():
                self.llm_model_var.set(st["model"])
            self.llm_local_label.config(text=text)
            self.llm_detect_btn.config(state="normal")
            self._refresh_badges()
```
In `_save`, replace the model-persisting loop with:
```python
            for pid, st in self._llm_state.items():
                model = st["model"].strip()
                cfg[f"llm_model_{pid}"] = "" if model == llm.PRESETS[pid].default_model else model
```
(The field already shows the preset default on open because `_build_llm_section` seeds `st["model"]` with `cfg value or preset.default_model`; blank stored + blank default for local presets yields an empty field, which is the intended "not picked yet" state.)

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py tests/gui/test_settings_discovery.py tests/gui/test_settings_crash_reporting.py -v` → all PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/ui/settings_dialog.py tests/gui/test_settings_llm.py
git commit -m "feat(settings): badge row, model combobox with Detect for Ollama/LM Studio, no default-id pinning on save"
```

---

### Task 5: Privacy and README wording, full gate

**Files:**
- Modify: `PRIVACY.md` (one bullet), `README.md` (Prerequisites bullet), `tests/smoke/test_privacy_dialog.py` (one assertion)

**Interfaces:** none new.

- [ ] **Step 1: Update the smoke assertion first**

In `tests/smoke/test_privacy_dialog.py::test_privacy_dialog_builds_and_shows_statement`, after the `"OpenRouter"` assertion add:
```python
        assert "Ollama / LM Studio (local)" in text_widgets[0].get("1.0", "end")
```
Run: `.venv\Scripts\python -m pytest tests/smoke/test_privacy_dialog.py -v` → that test FAILS.

- [ ] **Step 2: PRIVACY.md**

After the `- **Custom endpoint** — …` bullet add:
```
- **Ollama / LM Studio (local)** — nothing is sent anywhere. The model runs on your own computer and your transcripts never leave it. CampaignScribe only talks to the runtime on `localhost`.
```

- [ ] **Step 3: README**

In "Prerequisites", extend the AI-provider bullet so it ends with:
```
  To run with no API cost and no data leaving your PC, install
  [Ollama](https://ollama.com) (or LM Studio), pull a model such as
  `ollama pull qwen2.5:14b`, and pick **Ollama (local)** in Settings → AI
  model; **Detect** lists the models you have installed. Models of 12B
  parameters and up give the best results for speaker identification.
```
In "Layout" → the Settings bullet, change "Claude, Google Gemini, OpenRouter or a custom OpenAI-compatible endpoint" to "Claude, Google Gemini, OpenRouter, a local Ollama / LM Studio model, or a custom OpenAI-compatible endpoint".

- [ ] **Step 4: Full gate**

```
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -m "not gui" -q
```
Expected: ruff clean; both runs green (full ≈ 318 + 19 + 6 + 3 + 8 + 1 ≈ 355).

- [ ] **Step 5: Commit**

```
git add PRIVACY.md README.md tests/smoke/test_privacy_dialog.py
git commit -m "docs: local runtime wording in PRIVACY.md and README"
```

- [ ] **Step 6: Hand back to the controller**

Report commits and counts. The controller runs the live smoke on this PC (Ollama with `qwen2.5:14b` is installed): open Settings → Ollama (local) → Detect lists the model → Test connection succeeds → a real transcript summary runs locally; stop Ollama → Test connection and the Summarize pre-flight show the "is Ollama running?" / "press Detect" hints. The PR body must include `Roadmap: Imagination-Industries-LLC/CampaignScribe-planning#9`.
