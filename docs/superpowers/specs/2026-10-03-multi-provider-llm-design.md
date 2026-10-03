# Multi-Provider LLM — Design

- **Status:** Designed (brainstorm 2026-10-03; decisions approved by Mike). Implements Feature Spec #5 from the ProtonDrive strategic folder.
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/multi-provider-llm`.
- **Planning issue:** private board #8 (Phase 2, area MF5 LLM & Models).
- **Source spec:** `H:\ProtonDrive\mrompel\My files\Audio Transcription\CampaignScribe\Feature Spec - Multi-Provider LLM Support.md` (2026-05-28). This document is the build-level source of truth.
- **Downstream dependents:** #6 Local LLM & Model Picker (reuses the OpenAI-compatible adapter pointed at localhost), #14 Summarize Cost Transparency (reads the active provider), #3 Privacy (provider list).

## Goal

Let users choose which LLM powers speaker identification and session summaries instead of hardcoded Anthropic Claude. v1 providers: **Anthropic** (default), **Google Gemini**, **OpenRouter**, plus a **Custom OpenAI-compatible** endpoint. Architected so OpenAI, Groq, DeepSeek and local servers (Ollama, LM Studio) are the same adapter with a different `base_url` and model.

Success criteria:
1. Switching provider in Settings takes effect on the next run (no restart).
2. API keys are stored per provider in Windows Credential Manager; the existing Anthropic key keeps working without re-entry.
3. A bad key, wrong URL, or empty response fails with a clear, provider-named message and no crash.
4. Both LLM tasks (speaker ID JSON and summaries) run on every provider; the existing test suite passes with a fake provider in place of the fake Anthropic client.
5. Zero change to the ML stack pins.

## Decisions (approved 2026-10-03)

| # | Decision | Rationale |
|---|---|---|
| 1 | Gemini via the **`google-genai`** SDK | `google-generativeai` (named in the May spec) is deprecated by Google. |
| 2 | Anthropic default model becomes **`claude-sonnet-5-5`**; all model ids live in config, not code constants | Current Sonnet; model ids churn, so they are editable with sensible defaults. |
| 3 | **One keyring entry per provider** (`llm_key_<provider>`), with a read-only fallback to the legacy `anthropic_api_key` entry | Clean separation; zero-risk if a user downgrades (no migration/delete of the old entry). |
| 4 | **Both speaker ID and summaries are switchable**, with a per-provider `json_mode` capability flag | Local LLM (#6) depends on speaker ID being provider-agnostic; weaker models get native JSON mode where the API offers it. |
| 5 | Timeout/retry policy generalised per adapter; the Anthropic adapter uses `anthropic.Timeout`, not `httpx.Timeout` | Works on the installed `anthropic` 0.109 and on the 1.x line now on PyPI (1.x rejects `httpx` objects). |
| 6 | Streaming, local-model auto-detect, cost estimates, and the `anthropic` 0.x→1.x upgrade are **out of scope** | Each is its own roadmap item or follow-up (see Follow-ups). |

## Architecture

```
app/core/llm/
  __init__.py            re-exports Provider, LLMError, get_provider, PRESETS
  base.py                Provider protocol + LLMError
  anthropic_provider.py  AnthropicProvider (absorbs claude_api.make_client policy)
  gemini_provider.py     GeminiProvider (google-genai)
  openai_compat_provider.py  OpenAICompatProvider (openai SDK, configurable base_url)
  factory.py             PRESETS table + get_provider(cfg) + provider_ready(cfg)
```

Data flow (unchanged shape, new seam):

```
UI worker thread
  -> provider = llm.get_provider(config.load_config())      # once per run
  -> speaker_id.identify_speakers(segments, speakers_doc, provider)
       -> provider.complete(prompt, max_tokens=1000, json_mode=True) -> str
       -> _extract_json_object(text)                        # unchanged
  -> summarizer.summarize_part(..., provider)
       -> provider.complete(prompt, max_tokens=4000) -> str
```

`app/core/claude_api.py` is **deleted**; its policy (120 s total / 10 s connect / 3 retries) moves into `AnthropicProvider`.

### `base.py`

```python
class Provider(Protocol):
    provider_id: str      # "anthropic" | "gemini" | "openrouter" | "custom"
    model: str            # editable model id from config
    display_name: str     # "Claude", "Google Gemini", "OpenRouter", "Custom (OpenAI-compatible)"
    supports_json_mode: bool

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str: ...

class LLMError(RuntimeError):
    def __init__(self, provider_id: str, message: str, *, kind: str = "error"): ...
    # kind in {"missing_key", "auth", "network", "empty", "error"} -- UI maps to a message
```

- `complete` is single-turn, text-in → text-out. No streaming. Adapters normalise parameter names and response shapes.
- Every adapter wraps SDK exceptions into `LLMError` so UI code never imports an SDK. Auth failures (401/403) map to `kind="auth"`, connection/timeout to `"network"`, empty candidates / no text block to `"empty"`.
- `json_mode=True` is a **request**, not a guarantee: adapters with `supports_json_mode=False` ignore it. The prompts already say "return only JSON" and `_extract_json_object` stays as the universal safety net.

### `anthropic_provider.py`

- Constructor: `AnthropicProvider(api_key, model)`. Lazy `import anthropic` inside the constructor (keeps startup fast and tests SDK-free), raises `LLMError(kind="missing_key")` on an empty key.
- Client: `anthropic.Anthropic(api_key=..., timeout=anthropic.Timeout(120.0, connect=10.0), max_retries=3)`.
- `complete`: `client.messages.create(model=self.model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])`; returns the concatenated text of all `text` content blocks (robust to a response that has more than one block). Checks `stop_reason`; a `refusal` raises `LLMError(kind="empty", ...)` with the stop reason in the message.
- `supports_json_mode = False` (prompt-level JSON only; Claude follows the instruction reliably and the extractor handles fences). Structured outputs with a schema are a possible later enhancement, not v1.

### `gemini_provider.py`

- Constructor: `GeminiProvider(api_key, model)`; lazy `from google import genai`; `genai.Client(api_key=...)`.
- `complete`: `client.models.generate_content(model=self.model, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=max_tokens, response_mime_type="application/json" if json_mode else None, safety_settings=_RELAXED))`.
  - `_RELAXED` sets the harassment / hate / sexually-explicit / dangerous categories to `BLOCK_NONE`. Tabletop transcripts are full of violence and profanity; default safety settings return an empty candidate and we would rather get text than a silent blank.
  - Returns `response.text`. If it is `None`/empty, raise `LLMError(kind="empty")` including `candidates[0].finish_reason` when present.
- Timeout: `http_options=types.HttpOptions(timeout=120_000)` (ms). Retries: the SDK retries on 429/5xx by default; no extra layer.
- `supports_json_mode = True`.
- Default model (config): `gemini-2.5-flash`. Editable.

### `openai_compat_provider.py`

- Constructor: `OpenAICompatProvider(api_key, model, base_url, *, provider_id, display_name, supports_json_mode)`; lazy `import openai`; `openai.OpenAI(api_key=api_key or "sk-none", base_url=base_url, timeout=120.0, max_retries=3)`.
  - `api_key` may legitimately be empty for a local server (#6); the SDK requires a non-empty string, hence the placeholder.
- `complete`: `client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, response_format={"type": "json_object"} if (json_mode and self.supports_json_mode) else NOT_GIVEN)`; returns `choices[0].message.content`, raising `LLMError(kind="empty")` when `None`.
- Extra headers for OpenRouter: `HTTP-Referer` = the repo URL and `X-Title` = "CampaignScribe" (OpenRouter attribution; harmless elsewhere, so set only when `provider_id == "openrouter"`).
- Used by two presets in v1: `openrouter` (`https://openrouter.ai/api/v1`, default model `anthropic/claude-sonnet-4.5` — the implementer confirms the id against `GET https://openrouter.ai/api/v1/models` and bumps to the newest Sonnet listed, `supports_json_mode=True`) and `custom` (user-supplied `base_url`, `supports_json_mode=False` by default — the safe assumption for unknown servers).

### `factory.py`

```python
@dataclass(frozen=True)
class Preset:
    provider_id: str
    display_name: str
    default_model: str
    needs_key: bool
    needs_base_url: bool
    supports_json_mode: bool
    privacy_url: str
    privacy_note: str      # one line used in PRIVACY dialog / notes, e.g. "Sent to Google Gemini"

PRESETS: dict[str, Preset]  # keys: anthropic, gemini, openrouter, custom  (ordered for the dropdown)

def get_provider(cfg: dict | None = None) -> Provider
def provider_ready(cfg: dict | None = None) -> bool     # key present (if needed) and base_url present (if needed)
def active_preset(cfg: dict | None = None) -> Preset
```

- `get_provider` reads `cfg["llm_provider"]`, the matching `llm_model_<id>`, `config.get_provider_key(id)` and (for `custom`) `llm_base_url_custom`, and instantiates the adapter. Unknown provider id → falls back to `anthropic` and logs via `config.log_exception` (defensive against a hand-edited config.json).
- `provider_ready` replaces the seven `if not config.get_anthropic_key()` checks in the UI.

## Config and secrets (`app/config.py`)

New `DEFAULT_CONFIG` keys (picked up automatically by the existing merge in `load_config`):

```python
"llm_provider": "anthropic",
"llm_model_anthropic": "claude-sonnet-5-5",
"llm_model_gemini": "gemini-2.5-flash",
"llm_model_openrouter": "anthropic/claude-sonnet-4.5",
"llm_model_custom": "",
"llm_base_url_custom": "",
```

Secrets:

```python
def save_provider_key(provider_id: str, key: str) -> None   # keyring username f"llm_key_{provider_id}"
def get_provider_key(provider_id: str) -> str
    # anthropic: if the new entry is empty, fall back to the legacy "anthropic_api_key" entry (read-only)
def save_anthropic_key / get_anthropic_key                  # kept as thin aliases over the anthropic provider entry
```

- `save_anthropic_key` writes the **new** entry only; the legacy entry is never written or deleted (Decision 3).
- `get_huggingface_token` is untouched.

## Call-site refactor

### `app/core/speaker_id.py`
- Delete `CLAUDE_MODEL` and `_client`. `_send(provider, prompt, max_tokens=4000, json_mode=True) -> str` calls `provider.complete(...)`.
- Public signatures change `api_key: str` → `provider: Provider`: `discover_speakers(segments, provider)`, `identify_speakers(segments, speakers_reference, provider)`, `refine_speakers(segments, speakers_reference, provider)`. All three pass `json_mode=True`.
- `_extract_json_object`, prompt templates and fallback returns are unchanged.

### `app/core/summarizer.py`
- Delete `CLAUDE_MODEL` and `_client`. `summarize_part(..., provider, ...)` and `consolidate_summaries(..., provider, ...)` call `provider.complete(prompt, max_tokens=4000)` (prose; `json_mode=False`).
- `write_docx(model_used=...)`: callers pass `f"{provider.display_name} · {provider.model}"`; the parameter default becomes `""`.

### UI workers (five call sites)
`transcribe_tab._worker`, `summarize_tab._worker` + the consolidate worker, `refine_tab._worker`, `edit_profile_window` discover worker:
- Replace `api_key = config.get_anthropic_key()` with `provider = llm.get_provider()` at the top of the worker; pass `provider` through.
- Pre-flight checks replace `config.get_anthropic_key()` with `llm.provider_ready()`; the error text becomes `f"Add your {preset.display_name} API key in Settings (⚙)."` (or "…base URL…" for custom).
- `except LLMError as e:` → status/messagebox shows `e` (already provider-named). Other exceptions keep their current handling.
- `app_window._refresh_banner` uses `llm.provider_ready()`; banner text names the active provider.

### `app/core/claude_api.py` → deleted. `tests/unit/test_claude_api.py` → replaced by `tests/unit/test_llm_anthropic.py`.

## Settings dialog (`app/ui/settings_dialog.py`)

New **"— AI model —"** section placed first (above the HuggingFace token row; the standalone "Anthropic API key" row is removed):

| Row | Widget | Behaviour |
|---|---|---|
| Provider | read-only `Combobox` of `PRESETS` display names | On change: stash the current provider's model/key/base_url into a per-provider dict, load the new provider's values. |
| Model | editable `Entry`, pre-filled from config or preset default | "Reset to default" link-button restores `preset.default_model`. |
| API key | `Entry(show="•")` + Show checkbox | Hidden (`grid_remove`) when `needs_key` is False (future local presets). |
| Base URL | `Entry` | Shown only when `needs_base_url` (custom). |
| Test connection | `Button` | Builds a provider from the **unsaved** dialog values, calls `complete("Reply with the single word OK.", max_tokens=5)` on a daemon thread, reports "✓ Connected (model)" or the `LLMError` message in an inline label. Button disabled while a test runs. |

Save: writes every provider's edited key via `save_provider_key` (only those touched), the model fields, `llm_provider`, and `llm_base_url_custom`. Leaving a key blank for a provider you are not using is fine; `provider_ready` only checks the active one. After save, `app_window._refresh_banner()` runs (existing hook).

The HuggingFace token row stays where it is, directly after the new section.

## Privacy (`PRIVACY.md`, `app/core/privacy.py`, Privacy dialog)

- `PRIVACY.md`: the "Sent to the Anthropic Claude API" section becomes **"Sent to your chosen AI provider (and why)"**. Same three bullets (speaker samples, full transcript, campaign context), then a sub-list naming each v1 provider with its policy link and one-line retention note, plus an explicit line that **OpenRouter forwards the request to the model vendor you pick (an extra routing hop)** and that a **Custom endpoint** goes wherever the user pointed it. The "Stays on your computer" bullet about keys becomes "Your AI-provider API keys and HuggingFace token".
- `privacy.py`: `ANTHROPIC_PRIVACY_URL` stays (About/Privacy dialog) and gains `GEMINI_PRIVACY_URL`, `OPENROUTER_PRIVACY_URL`. `NOTE_SAMPLES` / `NOTE_TRANSCRIPT` become functions `note_samples(display_name)` / `note_transcript(display_name)`; the three tabs that call `add_privacy_note` refresh the note text in their `on_show()` from `llm.active_preset().display_name`.
- Privacy dialog (`app_window._show_privacy`): the single "Anthropic Privacy Policy" button becomes one button per v1 provider.

## Dependencies and packaging

- `requirements.txt`: add `google-genai`, `openai` (unpinned, like `anthropic`; both are small pure-Python SDKs and not in the ML tier).
- `setup_venv.bat` step 1 list: add `google-genai openai`.
- `requirements-dev.txt`: add `google-genai>=2.28.0`, `openai>=3.24.0` (the versions current on PyPI at design time; floors, like the rest of that file).
- `build.bat` / `CampaignScribe.spec`: `--hidden-import=google.genai --hidden-import=openai` and `--collect-data google.genai` if the SDK ships data files (verified during the packaging task).
- `.github/dependabot.yml`: no change — the ignore list targets the ML stack only.

## Testing

Unit (Tk-free):
- `test_llm_anthropic.py`: empty key → `LLMError(missing_key)`; client constructed with `anthropic.Timeout(120, connect=10)` and `max_retries=3` (fake `anthropic.Anthropic` captures kwargs, mirroring the current test); multi-block text concatenation; `stop_reason="refusal"` → `LLMError(empty)`.
- `test_llm_gemini.py`: json_mode sets `response_mime_type`; relaxed safety settings present; `response.text is None` → `LLMError(empty)` carrying the finish reason.
- `test_llm_openai_compat.py`: `response_format` sent only when json_mode and `supports_json_mode`; placeholder key for empty `api_key`; OpenRouter headers only for `provider_id="openrouter"`; `content is None` → `LLMError(empty)`.
- `test_llm_factory.py`: every preset instantiates from a config dict; unknown id falls back to anthropic; `provider_ready` truth table (key / base_url / neither).
- `test_config_llm.py`: new defaults merge into an old `config.json`; per-provider keyring round-trip; legacy `anthropic_api_key` fallback (set only the old entry → `get_provider_key("anthropic")` returns it; set the new entry → it wins).
- `test_speaker_id.py`, `test_summarizer*.py`, `test_pipeline.py`: switch from `fake_claude` to the new `fake_provider` fixture (below). Assertions on queued responses and `.calls` continue to work; new assertions check `json_mode=True` for the three speaker-ID calls and `False` for summaries.

Fixture change (`tests/conftest.py`): `fake_claude` is replaced by `fake_provider(responses, *, supports_json_mode=True)` which installs a `ScriptedProvider` via `monkeypatch.setattr("app.core.llm.factory.get_provider", ...)` and returns it; `.calls` records `(prompt, max_tokens, json_mode)`.

GUI (`-m gui`):
- `test_settings_llm.py`: provider switch swaps model/key fields; base URL row visible only for custom; Test connection reports success and an `LLMError` (scripted provider); Save persists per-provider keys and `llm_provider`.
- Existing banner / stage-tab tests updated for `provider_ready`.

Manual smoke (release gate for this PR, run from source): one real transcript through **Claude, Gemini, and OpenRouter** — speaker ID returns usable JSON and a summary + consolidated `.docx` is produced on each; wrong key on each → provider-named error, no crash.

## Error handling summary

| Situation | Where caught | User sees |
|---|---|---|
| No key / base URL for the active provider | pre-flight `provider_ready` | "Add your Gemini API key in Settings (⚙)." |
| 401/403 | adapter → `LLMError(auth)` | "Google Gemini rejected the API key. Check Settings." |
| Timeout / connection | adapter → `LLMError(network)` after SDK retries | "Could not reach OpenRouter (network timeout)." |
| Empty / blocked response | adapter → `LLMError(empty)` | "Claude returned no text (stop reason: refusal)." |
| Non-JSON text on a speaker-ID call | `_extract_json_object` fails → existing fallbacks | unchanged (identity mapping / empty suggestions) |
| Hand-edited bad `llm_provider` | factory fallback + `log_exception` | runs on Anthropic; errors.log notes the fallback |

## Follow-ups (not in this PR)

- **Anthropic SDK 0.x → 1.x upgrade**: `requirements.txt` has no pin, so a fresh `setup_venv.bat` already resolves 1.11.x; this design is 1.x-safe (Decision 5) but the upgrade itself (pin, `httpx2`, test fakes) should be a separate chore PR. Dependabot #45 (`anthropic>=0.111.0`) can merge independently.
- **#6 Local LLM**: add `ollama` / `lmstudio` presets to `PRESETS` (localhost `base_url`, `needs_key=False`), model auto-detect, annotated picker.
- **#14 Cost Transparency**: per-preset pricing table keyed by `provider_id` + model.
- Structured outputs with a schema for the Anthropic adapter if speaker-ID JSON reliability ever becomes a problem on Claude (it has not been).
- Privacy provider list refresh is done here for v1 providers; #6 adds the "stays on your device" line for local.

## Out of scope

Streaming; per-provider fine-tuning; automatic model routing; subscription-linking (ruled out by ToS, see Feature Spec #6); any change to the WhisperX / pyannote / torch pins.
