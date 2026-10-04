"""Pre-flight size/cost estimate for LLM runs (pure, Tk-free).

Input tokens ~= chars / 4; output is an upper bound (parts x max_tokens). Rates
come from the preset defaults or a per-provider user override in config.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app import config
from app.core.llm.factory import Preset

CHARS_PER_TOKEN = 4.0
CONTEXT_ALLOWANCE_CHARS = 2_000  # campaign/speaker context block + prompt framing
DEFAULT_MAX_OUTPUT_TOKENS = 4000  # summarizer's per-part max_tokens


@dataclass(frozen=True)
class Rates:
    input_per_mtok: float
    output_per_mtok: float
    known: bool  # False -> no $ figure can be computed
    free: bool  # local runtime -> "Free · local compute"


@dataclass(frozen=True)
class Estimate:
    input_tokens: int
    output_tokens_upper: int
    num_parts: int
    cost_upper: float | None  # None when rates unknown; 0.0 when free
    free: bool


def _valid_pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        i, o = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if i < 0 or o < 0 or math.isnan(i) or math.isnan(o):
        return None
    return i, o


def rates_for(preset: Preset, cfg: dict[str, Any] | None = None) -> Rates:
    """Preset default rates, or the user's per-provider override from config."""
    if preset.local_runtime:
        return Rates(0.0, 0.0, known=True, free=True)
    c = cfg if cfg is not None else config.load_config()
    overrides = c.get("llm_rates")
    pair = _valid_pair(overrides.get(preset.provider_id)) if isinstance(overrides, dict) else None
    if pair is None:
        pair = (float(preset.input_per_mtok), float(preset.output_per_mtok))
    i, o = pair
    return Rates(i, o, known=not (i == 0 and o == 0), free=False)


def estimate(
    total_chars: int,
    num_parts: int,
    rates: Rates,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> Estimate:
    if num_parts <= 0 or total_chars <= 0:
        return Estimate(
            0, 0, max(num_parts, 0), 0.0 if (rates.known or rates.free) else None, rates.free
        )
    input_tokens = math.ceil(total_chars / CHARS_PER_TOKEN)
    output_upper = num_parts * max_output_tokens
    if rates.free:
        cost_upper: float | None = 0.0
    elif not rates.known:
        cost_upper = None
    else:
        cost_upper = (input_tokens / 1e6) * rates.input_per_mtok + (
            output_upper / 1e6
        ) * rates.output_per_mtok
    return Estimate(input_tokens, output_upper, num_parts, cost_upper, rates.free)


def fmt_tokens(n: int) -> str:
    return f"~{round(n / 1000)}k" if n >= 1000 else f"~{n}"


def fmt_dollars(x: float) -> str:
    if 0 < x < 0.01:
        return "<$0.01"
    # Use round-half-up for proper rounding behavior
    rounded = math.floor(x * 100 + 0.5) / 100
    return f"${rounded:.2f}"


def fmt_rate(x: float) -> str:
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s or "0"


def format_line(est: Estimate, preset: Preset, rates: Rates) -> str:
    if est.num_parts == 0:
        return "Add transcript files to see an estimate."
    head = f"Estimate: {fmt_tokens(est.input_tokens)} input tokens · up to {fmt_tokens(est.output_tokens_upper)} output"
    if est.free:
        return f"{head} · Free · local compute ({preset.display_name})"
    if est.cost_upper is None:
        return f"{head} · cost unknown — set {preset.display_name} rates in Settings (⚙)"
    return (
        f"{head} · est. up to ~{fmt_dollars(est.cost_upper)} "
        f"({preset.display_name} @ ${fmt_rate(rates.input_per_mtok)}/${fmt_rate(rates.output_per_mtok)} per M)"
        " · + one more call when you consolidate"
    )


def format_confirm(est: Estimate, preset: Preset, rates: Rates) -> str:
    return (
        f"This will send {fmt_tokens(est.input_tokens)} input tokens to {preset.display_name} and "
        f"generate up to {fmt_tokens(est.output_tokens_upper)} output tokens across {est.num_parts} part(s).\n"
        f"Estimated cost: up to ~{fmt_dollars(est.cost_upper or 0.0)} (approximate, at your configured rates)."
        "\n\nContinue?"
    )
