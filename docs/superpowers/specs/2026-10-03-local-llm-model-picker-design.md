# Local LLM Support & Annotated Model Picker — Design

- **Status:** Designed (brainstorm 2026-10-03; approach A approved by Mike). Implements Feature Spec #6 from the ProtonDrive strategic folder.
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/local-llm-model-picker`.
- **Planning issue:** private board #9 (Phase 2, area MF5 LLM & Models).
- **Source spec:** `H:\ProtonDrive\mrompel\My files\Audio Transcription\CampaignScribe\Feature Spec - Local LLM and Model Picker.md` (2026-05-28). This document is the build-level source of truth.
- **Builds on:** `docs/superpowers/specs/2026-10-03-multi-provider-llm-design.md` (merged as PR #52): `app/core/llm/` with `Preset`/`PRESETS`, `OpenAICompatProvider`, `make_provider`/`get_provider`/`provider_ready`/`not_ready_message`, and the Settings "AI model" section.
- **Downstream:** #14 Summarize Cost Transparency reads the cost badge; planning #24 (privacy upkeep) closes with this feature's "stays on your device" line.

## Goal

Let users run speaker identification and summaries on a **local model** so there is no per-token cost and transcripts never leave the machine, and make every model choice carry explicit **Key / Cost / Privacy / Quality** signals. Ollama is primary, LM Studio supported, any other OpenAI-compatible local server via the existing Custom endpoint preset.

Success criteria:
1. With Ollama running and a model pulled, Settings detects the installed models, the user picks one with no API key, and a summary generates locally.
2. With no runtime running, selecting Ollama / LM Studio shows a plain "start it, then Detect" message in Settings and the same sentence in pre-flight; no crash, no silent hang.
3. The badge row shows the right four signals for every preset (e.g. Claude: key required · $$ per token · Sent to Anthropic · Frontier; Ollama qwen2.5:14b: no key · Free, local compute · Stays on your device · Good).
4. Existing cloud behaviour is unchanged; the 318-test suite stays green; ML pins untouched.

## Decisions (approved 2026-10-03)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Approach A — extend the existing picker**: two new presets in the provider dropdown, an editable model combobox filled by a Detect button, and a one-line badge row. No separate unified table. | Reuses the Multi-Provider section as built; one place for all provider settings; the "unified chooser" of the May spec is satisfied by the dropdown + badges. |
| 2 | Badge text for cloud presets is **hardcoded in `PRESETS`** for v1; local Quality is **derived from parameter size**. | Model lists churn; an editable table is worth building when Cost Transparency (#14) becomes the second consumer. |
| 3 | Local presets reuse `OpenAICompatProvider`; JSON mode **on for Ollama, off for LM Studio** until verified live. | Ollama's `/v1` honours `response_format: json_object`; LM Studio's support varies by version. |
| 4 | Local presets get a **longer per-call timeout (600 s)** via a new `timeout_s` preset field. | A 14B model summarising a 4000-token part can exceed 120 s on CPU-only machines. |
| 5 | **Stop pinning default model ids into config on save** (vault backlog item): `_save` writes `""` when the field equals the preset default; `make_provider` already resolves blank → default. Local presets have `default_model=""`, so blank means "not chosen yet". | Local model lists are dynamic, so the old "always write a concrete id" rule has no sensible value for them; and cloud users who never customised now receive future default bumps. |
| 6 | Not in scope: bundling/auto-downloading weights, subscription linking, fine-tuning, `max_completion_tokens` for OpenAI reasoning models (stays in the vault backlog), GPU/VRAM auto-sizing. | Per the May spec and the PR #52 follow-ups. |

## Architecture

```
app/core/llm/
  local_detect.py        NEW  probe Ollama / LM Studio, list models (Tk-free, urllib, short timeout)
  factory.py             MOD  Preset gains badge fields + timeout_s; two local presets; BASE_URLS; readiness messages
  openai_compat_provider.py  MOD  accepts timeout_s (default unchanged)
app/config.py            MOD  llm_model_ollama / llm_model_lmstudio defaults ""
app/ui/settings_dialog.py  MOD  badge row, model Combobox, Detect button, local caveat, save-blank-when-default
app/core/privacy.py, PRIVACY.md  MOD  "stays on your device" wording for local presets
```

Data flow (unchanged shape): UI workers call `llm.get_provider()`; for `ollama`/`lmstudio` the factory returns an `OpenAICompatProvider` pointed at localhost with no key. Detection is a Settings-only concern.

### `local_detect.py`

```python
@dataclass(frozen=True)
class LocalModel:
    model_id: str          # "qwen2.5:14b" (Ollama) / "qwen2.5-14b-instruct" (LM Studio)
    parameter_size: str    # "14.8B" when the runtime reports it, else ""

@dataclass(frozen=True)
class DetectResult:
    runtime_id: str        # "ollama" | "lmstudio"
    running: bool
    models: list[LocalModel]
    error: str             # "" when running; otherwise a one-line reason (connection refused, timeout, bad JSON)

def detect(runtime_id: str, *, base_url: str | None = None, timeout_s: float = 1.5) -> DetectResult
def quality_label(parameter_size: str) -> str   # "" -> "Basic"; < 12B -> "Basic"; >= 12B -> "Good"
```

- `ollama`: `GET {base_url_root}/api/tags` → `{"models":[{"name": ..., "details": {"parameter_size": "14.8B"}}]}`. `base_url_root` is the preset base URL with the trailing `/v1` removed (`http://localhost:11434`).
- `lmstudio`: `GET {base_url}/models` → `{"data":[{"id": ...}]}`; no size → `parameter_size=""`.
- Pure `urllib.request` with `timeout_s`; every exception (URLError, timeout, JSON error, unexpected shape) becomes `running=False` with `error` set. Never raises. Tk-free, no SDK import.
- `quality_label` parses the leading number of strings like `"14.8B"`, `"7B"`, `"8.0B"`; unparseable → `"Basic"`.

### `factory.py`

`Preset` gains four fields (all presets updated):

```python
key_label: str        # "API key required" | "No key needed"
cost_label: str       # "$$ per token" | "¢ per token" | "Varies by model" | "Free · local compute"
quality_label: str    # "Frontier" | "Strong" | "Varies by model" | "" (local: derived per model)
timeout_s: float      # 120.0 cloud, 600.0 local
local_runtime: str    # "" for cloud/custom; "ollama" | "lmstudio" for the two local presets
```

New presets (dropdown order: Claude, Google Gemini, OpenRouter, **Ollama (local)**, **LM Studio (local)**, Custom endpoint):

| id | display_name | vendor_label | default_model | needs_key | needs_base_url | json | base URL | timeout |
|---|---|---|---|---|---|---|---|---|
| `ollama` | Ollama (local) | your own computer (Ollama) | `""` | False | False | True | `http://localhost:11434/v1` | 600 |
| `lmstudio` | LM Studio (local) | your own computer (LM Studio) | `""` | False | False | False | `http://localhost:1234/v1` | 600 |

Cloud badge values: Claude `API key required · $$ per token · Frontier`; Gemini `API key required · ¢ per token · Strong`; OpenRouter `API key required · Varies by model · Varies by model`; Custom `Key optional · Varies · Varies`.

- `make_provider`: passes `timeout_s=preset.timeout_s` to `OpenAICompatProvider`; for local presets a blank model raises `LLMError(kind="missing_key", message="Pick a model under Settings → AI model (press Detect with <runtime> running).")`.
- `not_ready_message`: for a preset with `local_runtime` and a blank `llm_model_<pid>` → `"Pick an {display_name} model in Settings (⚙): start {runtime} and press Detect."`. Readiness does **not** probe the network (pre-flight stays instant); a stopped runtime surfaces as `LLMError(kind="network")` from the adapter with the message `"Could not reach Ollama (local) — is Ollama running?"` (the compat adapter's network error gets the runtime hint when `local_runtime` is set).
- `badges_for(preset, model_id, parameter_size="") -> list[str]` returns the four strings in order Key, Cost, Privacy, Quality; Privacy is `"Stays on your device"` for local presets, else `f"Sent to {vendor_label}"`; Quality for local presets comes from `local_detect.quality_label(parameter_size)`.

### `openai_compat_provider.py`

Constructor gains `timeout_s: float = _TIMEOUT_TOTAL` (keyword) and passes it to `openai.OpenAI(timeout=...)`; the network-error message appends `" — is {display_name} running?"` when the provider was built for a local runtime (`local_runtime` passed through as a keyword, default `""`). No other change.

## Config and secrets

`DEFAULT_CONFIG` gains `"llm_model_ollama": ""` and `"llm_model_lmstudio": ""`. No keyring entries for local presets (`needs_key=False`; `get_provider_key` returns `""`).

`SettingsDialog._save` (Decision 5): `cfg[f"llm_model_{pid}"] = "" if model.strip() == preset.default_model else model.strip()`. On open, a blank stored model shows the preset default in the field (unchanged behaviour); for local presets the field shows the empty combobox until Detect runs or the user types an id.

## Settings dialog

Within the existing "AI model" section:

| Row | Change |
|---|---|
| Provider | dropdown now lists six presets in the order above. |
| **Badges** (new, directly under Provider) | one `ttk.Label` `llm_badge_label`, text `" · ".join(badges_for(...))`, refreshed on provider change, on model change (`<KeyRelease>`/`<<ComboboxSelected>>`), and after Detect. |
| Model | `ttk.Entry` becomes `ttk.Combobox` (editable, `state="normal"`) `llm_model_combo`; `values` filled by Detect for local presets, empty list otherwise. The "Default" button stays (no-op for local presets whose default is blank). |
| **Detect** (new button, same row as Model, shown only for local presets) | runs `local_detect.detect(runtime)` on a daemon thread; result applied via `after` with the same `winfo_exists` guard as Test connection. Success: fills `values`, selects the first model if the field was blank, badge row updates, caveat label shows `"{n} models found. Small models (< 12B) may struggle with the strict speaker-ID JSON; summaries are fine."`. Failure: caveat shows `"{display_name} not running — start it, then press Detect. ({error})"`. Auto-runs once when a local preset is selected. |
| API key / Base URL rows | hidden (`grid_remove`) for local presets (`needs_key=False`, `needs_base_url=False`). |
| Test connection | unchanged; the probe now runs against the local server with the preset timeout. |

Per-provider state (`_llm_state[pid]`) gains `"detected": list[LocalModel]` so switching away and back keeps the detected list without re-probing.

## Pre-flight and workers

No worker code changes. The five call sites already go through `provider_ready()` / `not_ready_message()` / `get_provider()`; the new readiness sentence and the runtime-hinted network error come from the factory and adapter.

## Privacy

- `PRIVACY.md` "Sent to your chosen AI provider" section gains, after the Custom bullet: **"Ollama / LM Studio (local)** — nothing is sent anywhere; the model runs on your own computer and your transcripts never leave it." The Custom bullet's local sentence stays.
- `privacy.py` note functions are unchanged; for local presets `vendor_label` reads "your own computer (Ollama)", so the Transcribe/Summarize/Refine notes read "Speaker samples are sent to your own computer (Ollama) for this step." — acceptable and accurate; no special-casing.
- Privacy dialog links unchanged (no vendor policy for local).

## Testing

Unit (Tk-free):
- `test_local_detect.py`: a `http.server` thread serving canned `/api/tags` and `/v1/models` JSON → models parsed with sizes; connection refused (unused port) → `running=False` with `error`; malformed JSON → `running=False`; `quality_label` table (`""`, `"7B"`, `"8.0B"`, `"12B"`, `"14.8B"`, `"junk"`).
- `test_llm_factory.py` additions: six presets in order; local presets `needs_key=False`, `default_model=""`, `timeout_s=600`; `make_provider("ollama", model="qwen2.5:14b", api_key="")` builds a compat provider with the localhost base URL and `supports_json_mode=True`; blank local model → `missing_key` LLMError; `badges_for` table for every preset; `not_ready_message` for `ollama` with/without a stored model; `DEFAULT_CONFIG` ↔ `PRESETS` default consistency test extended.
- `test_llm_openai_compat.py` additions: `timeout_s` reaches the client; local network error carries "is Ollama (local) running?".
- `test_config_llm.py`: new defaults merge.

GUI:
- `test_settings_llm.py` additions: selecting Ollama hides key/base-URL rows and shows Detect; a scripted `detect` (monkeypatched) fills the combobox and selects the first model; failure path shows the "not running" caveat; badge label text for Claude vs Ollama; save writes `""` when the model equals the preset default and the typed id otherwise; Detect result after dialog destroy is ignored.
- Smoke `test_privacy_dialog.py`: local wording present in PRIVACY.md.

Live (this PC has Ollama with `qwen2.5:14b`): Detect lists it; Test connection succeeds; a real transcript summary runs locally; with Ollama stopped, Test connection and the Summarize pre-flight show the runtime hint.

## Error handling summary

| Situation | Where | User sees |
|---|---|---|
| Local preset, no model chosen | `not_ready_message` | "Pick an Ollama (local) model in Settings (⚙): start Ollama and press Detect." |
| Runtime not running at Detect | `local_detect` → Settings caveat | "Ollama (local) not running — start it, then press Detect. (connection refused)" |
| Runtime not running at run time | adapter `network_error` | "Could not reach Ollama (local) — is Ollama running?" |
| Model id typed that the runtime lacks | adapter `generic_error` (HTTP 404 from Ollama) | "Ollama (local) error: HTTP 404" (the Detect list is the fix) |
| Slow local generation | adapter timeout 600 s | "Could not reach Ollama (local) (APITimeoutError) — is Ollama running?" |

## Follow-ups (not in this PR)

- Cost Transparency (#14): consume `cost_label` and add per-model rates.
- `max_completion_tokens` for OpenAI reasoning models via a per-preset token-parameter field (vault backlog).
- Editable badge table in config once a second consumer exists.
- VRAM-aware recommendations ("your GPU can run up to ~14B") — needs the GPU info already collected by `check_gpu()`.

## Out of scope

Bundling or auto-downloading model weights; subscription-credential proxies (ToS); fine-tuning; any change to the WhisperX / pyannote / torch pins.
