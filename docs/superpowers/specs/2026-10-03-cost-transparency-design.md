# Summarize Cost Transparency — Design

- **Status:** Designed (brainstorm 2026-10-03; per-provider pricing approved by Mike). Implements Feature Spec #14 from the ProtonDrive strategic folder, updated for the provider seam.
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/cost-transparency`.
- **Planning issue:** private board #10 (Phase 2, area MF5 LLM & Models).
- **Source spec:** `H:\ProtonDrive\mrompel\My files\Audio Transcription\CampaignScribe\Feature Spec - Summarize Cost Transparency.md` (2026-05-28, single-provider). This document supersedes its Design section.
- **Builds on:** `app/core/llm/` (`Preset`/`PRESETS` with `cost_label`, `active_preset`, local presets with `local_runtime`), the Settings "AI model" section (badge row, per-provider state), and the Summarize tab (`app/ui/summarize_tab.py`).

## Goal

Before a summary run spends money, show the user a rough size and cost and ask once. Local runs are free and say so with no gate.

Success criteria:
1. A live estimate line above **Start Summarization** updates when transcript files are added/removed/cleared, when the prompt changes, and after Settings closes.
2. Editing a provider's rates in Settings changes the estimate immediately on the next refresh; a bad entry falls back to the preset default.
3. On a cloud provider with known rates, Start shows a yes/no confirmation with the same numbers; **No** aborts without starting the worker. On Ollama / LM Studio (free) and on providers with unknown rates, Start runs without a dialog (unknown-rate runs show "cost unknown" in the line instead).
4. Existing behaviour otherwise unchanged; suite stays green; no new dependencies.

## Decisions (approved 2026-10-03)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Per-provider rates**, not per-model: each preset carries default input/output $ per million tokens for its default model; Settings lets the user override per provider. | Mirrors the picker's per-provider state; model churn is handled by the user editing two numbers. A per-model table is a second thing to maintain with no second consumer yet. |
| 2 | Estimate = `chars / chars_per_token` input tokens (default 4; see #5; plus prompt and a fixed context allowance, per part) and `parts × 4000` output tokens as an **upper bound**; wording always says "up to ~" and "approximate". | The May spec's heuristic; exact tokenization is out of scope. |
| 3 | Confirmation dialog only when the estimate carries a dollar figure above zero. Local presets and unknown-rate providers never prompt. | The gate exists to prevent surprise spend; a free run has none, and an unknown-rate run already warns in the line. |
| 4 | Rates live in one config key `llm_rates: dict[str, list[float]]` (`{pid: [in, out]}`), blank = preset default. | One key, nested JSON, merges cleanly through the existing `load_config` top-level merge. |
| 5 | Input tokens = `chars / chars_per_token`, a per-preset `Preset.chars_per_token`: anthropic `2.5` (measured 2.69 on claude-sonnet-5-5, rounded down so it stays an upper bound), openrouter `3.0` (older Sonnet tokenizer, unmeasured), all others `4.0`. The prompt and a `CONTEXT_ALLOWANCE_CHARS = 3_000` context block are counted once **per part**, since each part's request carries them. | A measured ratio showed `chars / 4` ran low for the default model; the dollar figure must be conservative. |
| 6 | The consolidation call is priced: `consolidate_upper` = part summaries in (`parts × 4000 + 500` prompt tokens) plus one 4000-token summary out. The label shows "+ up to ~$X more when you consolidate" and the confirm dialog adds a line. | Disclosed-but-unpriced was a review finding. |
| 7 | An explicit valid `[0, 0]` override on a cloud provider means **known** zero cost (e.g. Gemini free tier): label shows `~$0.00`, no gate. Without an override, 0/0 defaults stay unknown. | The user said it, so it is not "unknown". |
| 8 | If the configured model differs from the preset's default model and no rate override exists, the known label appends a hint (`model_rate_hint`) that the rates shown are for the default model. | Default rates would otherwise silently apply to a different model. |
| 9 | Estimates on Transcribe/Refine, actual usage read back from responses, and exact token counting are **out of scope** (follow-ups). | Per the May spec; usage read-back needs adapter changes. |

## Architecture

```
app/core/llm/cost.py        NEW  Rates, rates_for(), estimate() — pure, Tk-free
app/core/llm/factory.py     MOD  Preset gains input_per_mtok / output_per_mtok defaults
app/core/llm/__init__.py    MOD  re-export cost
app/config.py               MOD  "llm_rates": {}
app/ui/settings_dialog.py   MOD  rate row (input/output $ per M) under the badge row, per-provider, hidden for local presets
app/ui/summarize_tab.py     MOD  estimate label above Start; recompute hooks; confirm gate in _start
```

### `cost.py`

```python
CHARS_PER_TOKEN = 4.0
CONTEXT_ALLOWANCE_CHARS = 3_000     # context block + prompt framing, counted per part
CONSOLIDATE_PROMPT_TOKENS = 500
DEFAULT_MAX_OUTPUT_TOKENS = 4000    # summarizer's per-part max_tokens

@dataclass(frozen=True)
class Rates:
    input_per_mtok: float
    output_per_mtok: float
    known: bool          # False -> rates unknown (custom with no override); cost has no $ figure
    free: bool           # True for local presets -> "Free · local compute"

@dataclass(frozen=True)
class Estimate:
    input_tokens: int
    output_tokens_upper: int
    num_parts: int
    cost_upper: float | None   # None when rates unknown; 0.0 when free
    free: bool

def rates_for(preset: Preset, cfg: dict | None = None) -> Rates
def estimate(total_chars: int, num_parts: int, rates: Rates, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS, chars_per_token: float = CHARS_PER_TOKEN) -> Estimate
def consolidate_upper(num_parts: int, rates: Rates, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS) -> float | None
def model_rate_hint(preset: Preset, cfg: dict | None = None) -> str
def format_line(est: Estimate, preset: Preset, rates: Rates, hint: str = "") -> str
def format_confirm(est: Estimate, preset: Preset, rates: Rates) -> str
```

- `rates_for`: local preset → `Rates(0, 0, known=True, free=True)`. Else read `cfg["llm_rates"].get(pid)`; a valid `[in, out]` pair of non-negative floats overrides (and is always `known`, even `[0, 0]`); otherwise the preset defaults. Without an override `known = not (input == 0 and output == 0)`, so custom (defaults 0/0) is unknown until the user sets rates.
- `estimate`: `input_tokens = ceil(total_chars / chars_per_token)`, `output_tokens_upper = num_parts * max_output_tokens`, `cost_upper = None if not known else (input/1e6)*in + (output/1e6)*out` (0.0 when free). `num_parts = 0` → zeros.
- `format_line` (the label):
  - no files: `"Add transcript files to see an estimate."`
  - free: `"Estimate: ~38k input tokens · up to ~8k output · Free · local compute (Ollama (local))"`
  - unknown: `"Estimate: ~38k input tokens · up to ~8k output · cost unknown — set Custom endpoint rates in Settings (⚙)"`
  - known: `"Estimate: ~38k input tokens · up to ~8k output · est. up to ~$0.16 (Claude @ $2/$10 per M) · + up to ~$0.06 more when you consolidate"` (`hint` from `model_rate_hint` is appended to this variant only)
  - Token counts render as `~Nk` for ≥ 1000 else `~N`; dollars as `$0.16` (two decimals, `< $0.01` shown as `"<$0.01"`).
- `format_confirm`: `"This will send ~38k input tokens to Claude and generate up to ~8k output tokens across 2 part(s).\nEstimated cost: up to ~$0.16 (approximate, at your configured rates).\nConsolidating afterwards makes one more call (up to ~$0.06).\n\nContinue?"`.

### `factory.py`

`Preset` gains `input_per_mtok: float = 0.0`, `output_per_mtok: float = 0.0`, `chars_per_token: float = 4.0`. Defaults: anthropic `2.0 / 10.0` (Claude Sonnet 5.5 list), gemini `0.30 / 2.50` (Gemini 2.5 Flash list), openrouter `3.0 / 15.0` (its default model is `anthropic/claude-sonnet-4.5`, a 4.x Sonnet), ollama/lmstudio `0 / 0` (free), custom `0 / 0` (unknown).

### Config

`DEFAULT_CONFIG["llm_rates"] = {}`. Settings writes `cfg["llm_rates"][pid] = [in, out]` only for providers the user edited; a cleared pair removes the key (back to default).

## Settings dialog

Under the badge row, a new **Rates** row (`llm_rates_row` Frame) for non-local presets: label `"Rates ($ per M tokens):"`, two `Entry`s `llm_rate_in_var` / `llm_rate_out_var` (width 8) labelled `in` / `out`, and a `Default` button restoring the preset's numbers. Per-provider state `st["rate_in"]`, `st["rate_out"]` (strings) seeded from `llm_rates` override or preset default; stashed/loaded on provider switch exactly like model/key. Hidden (`grid_remove`) for local presets (free) — the badge row already says so. On save: parse both as floats ≥ 0; if either fails or both equal the preset defaults → drop the override (`llm_rates.pop(pid)`), else store `[in, out]`. No network, no SDK.

## Summarize tab

- New `self.estimate_var` + `ttk.Label(style=LBL_DIM, wraplength=760)` at **row 6**; Start → row 7, Cancel/status → row 8, output frame → row 9 (and the trailing `rowconfigure`, if any, follows).
- `_refresh_estimate()`: `total_chars = sum(file sizes) + num_parts * (len(selected prompt content) + CONTEXT_ALLOWANCE_CHARS)`; `num_parts = len(self.transcript_files)`; `preset = llm.active_preset()`; `rates = cost.rates_for(preset)`; `self.estimate_var.set(cost.format_line(..., hint=cost.model_rate_hint(preset)))`. Called at the end of `__init__`, from `_add_files`, `_remove_selected`, `_clear_files`, `_on_prompt_select`, `load_for_session`, `on_settings_changed`, and after Edit Selected returns.
- `_start`: after the existing validations (profile, files, provider ready, output folder) and before any UI reset, compute the same estimate; if `est.cost_upper` is a number `> 0` → `messagebox.askyesno("Confirm cost", cost.format_confirm(...))`; `False` → `return`. Free / unknown → no dialog.
- No change to the worker, consolidation, or docx code.

## Error handling

| Situation | Behaviour |
|---|---|
| Transcript path no longer exists | skipped in the size sum (no crash); the run itself already reports the read error |
| Bad rate text in Settings | falls back to preset default on save; estimate never raises |
| `llm_rates` hand-edited to a non-dict / wrong shape | `rates_for` ignores it and uses defaults |
| Unknown provider id in config | `active_preset()` already falls back to anthropic |

## Testing

Unit (`tests/unit/test_llm_cost.py`): `rates_for` for each preset class (cloud default, cloud override, bad override shape, local free, custom unknown); `estimate` math incl. zero parts and ceil; `format_line` for the four wordings and the `k` / `<$0.01` formatting; `format_confirm` text. `tests/unit/test_llm_factory.py`: preset rate defaults. `tests/unit/test_config_llm.py`: `llm_rates` default `{}` and round-trip.

GUI: `tests/gui/test_settings_llm.py` — rate row hidden for Ollama, shown for Claude with defaults `2.0`/`10.0`; editing persists `llm_rates["anthropic"] == [3.0, 15.0]`; Default button restores; bad text drops the override; switching providers keeps edits. `tests/gui/test_summarize_cost.py` (new) — label reads the empty-state text with no files; adding a tmp transcript file sets a `k`-formatted estimate with a `$` figure on Claude; switching config to `ollama` + `on_settings_changed()` shows "Free · local compute"; `_start` with a patched `messagebox.askyesno` returning False does not start the worker (patch `threading.Thread` to record), returning True does; on `ollama` the dialog is never called.

Manual: one real run on Claude from `run_dev.bat` to eyeball the line and the dialog.

## Follow-ups

- Actual token usage read back from provider responses (adapters would return usage; show "actual: $0.11" in the status line after a run).
- Transcribe / Refine / Discover estimates (speaker-ID calls are small; same helper).
- Per-model rate table once a second consumer exists.

## Out of scope

Exact tokenization; billing integration; changing `max_tokens`; any ML-stack change.
