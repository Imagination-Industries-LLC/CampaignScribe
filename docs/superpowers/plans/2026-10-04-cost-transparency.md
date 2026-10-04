# Summarize Cost Transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a live, provider-aware size-and-cost estimate above Start Summarization, let users set per-provider rates in Settings, and confirm once before any run that would cost money.

**Architecture:** A pure Tk-free module `app/core/llm/cost.py` resolves rates (preset default or per-provider user override from one config key) and computes a `chars/4` input estimate with a `parts × 4000` output upper bound, plus the exact label and dialog wording. `Preset` gains default rates. Settings gets a per-provider rate row under the badges (hidden for local presets). The Summarize tab gets an estimate label, recompute hooks on every input change, and a yes/no gate in `_start` that fires only when the estimate carries a dollar figure above zero.

**Tech Stack:** Python 3.11, Tkinter/ttk, pytest. Windows + PowerShell 5.1; run everything through `.venv\Scripts\python`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-03-cost-transparency-design.md` — read it first.

## Global Constraints

- Branch `feature/cost-transparency` off `main` (spec already committed). One PR at the end; Mike merges.
- Every commit: `.venv\Scripts\python -m ruff check .` and `.venv\Scripts\python -m ruff format .` clean first. Also run `.venv\Scripts\python -m bandit -q -r app -ll` before the final commit (CI fails on Medium+). Single-line commit messages. **No AI attribution, no `Co-Authored-By`.**
- `.venv\Scripts\python -m pytest -q` (full, GUI included) must stay green after every task (368 at branch start).
- No new runtime dependencies; ML pins untouched; `.github/dependabot.yml` untouched. UI imports only `from app.core import llm` and `from app.core.llm import cost`.
- Constants exactly: `CHARS_PER_TOKEN = 4.0`, `CONTEXT_ALLOWANCE_CHARS = 2_000`, `DEFAULT_MAX_OUTPUT_TOKENS = 4000`. Preset default rates ($ per million tokens, input / output): anthropic `2.0 / 10.0`, gemini `0.30 / 2.50`, openrouter `2.0 / 10.0`, ollama `0 / 0`, lmstudio `0 / 0`, custom `0 / 0`.
- Config key `llm_rates: dict[str, list[float]]` (`{pid: [in, out]}`), default `{}`; an override equal to the preset defaults, or cleared/invalid, is dropped on save.
- Wording (exact; see Task 1 for the formatter): no files → `Add transcript files to see an estimate.`; free → `Estimate: ~38k input tokens · up to ~8k output · Free · local compute (Ollama (local))`; unknown → `Estimate: … · cost unknown — set Custom endpoint rates in Settings (⚙)`; known → `Estimate: … · est. up to ~$0.16 (Claude @ $2/$10 per M) · + one more call when you consolidate`. Token counts `~Nk` at ≥ 1000 else `~N`; dollars two decimals, below one cent as `<$0.01`; rates in the label print without trailing zeros (`$2/$10`, `$0.3/$2.5`).
- Confirm dialog (title `Confirm cost`) only when `estimate.cost_upper` is a number `> 0`; local and unknown never prompt.
- No references to the predecessor product name.

## Review Focus

1. A hand-edited `llm_rates` value of the wrong shape (a string, a one-element list, negative numbers, non-numeric strings) must fall back to defaults, never crash the Summarize tab. → Task 1 `test_rates_for_ignores_bad_override_shapes`.
2. A transcript path removed from disk after being added must be skipped by the size sum, not crash the estimate. → Task 3 `test_estimate_skips_missing_files`.
3. A cost that rounds below one cent must render as `<$0.01`, never `$0.00` (which would read as free). → Task 1 `test_format_sub_cent`; the Start gate uses `> 0`, so it still prompts (pinned by the gate rule in Task 3's confirm test).
4. Rate fields typed with a comma decimal or a dollar sign (`2,5`, `$2`) must not be stored as garbage; they fall back to defaults. → Task 2 `test_bad_rate_text_drops_override`.
5. Re-entering exactly the default rates must remove the override so future default bumps reach the user. → Task 2 `test_default_rates_remove_override`.

---

### Task 1: `cost.py`, preset rate defaults, config key

**Files:**
- Create: `app/core/llm/cost.py`
- Modify: `app/core/llm/factory.py` (two `Preset` fields + per-preset values)
- Modify: `app/core/llm/__init__.py` (re-export `cost`)
- Modify: `app/config.py` (`"llm_rates": {}`)
- Test: `tests/unit/test_llm_cost.py` (new), `tests/unit/test_llm_factory.py` (one test), `tests/unit/test_config_llm.py` (extend one test)

**Interfaces:**
- Produces: `cost.Rates(input_per_mtok: float, output_per_mtok: float, known: bool, free: bool)`, `cost.Estimate(input_tokens: int, output_tokens_upper: int, num_parts: int, cost_upper: float | None, free: bool)`, `cost.rates_for(preset, cfg=None) -> Rates`, `cost.estimate(total_chars, num_parts, rates, max_output_tokens=4000) -> Estimate`, `cost.format_line(est, preset, rates) -> str`, `cost.format_confirm(est, preset, rates) -> str`, `cost.fmt_tokens(n) -> str`, `cost.fmt_dollars(x) -> str`, `cost.fmt_rate(x) -> str`, constants `CHARS_PER_TOKEN`, `CONTEXT_ALLOWANCE_CHARS`, `DEFAULT_MAX_OUTPUT_TOKENS`. `Preset.input_per_mtok`, `Preset.output_per_mtok`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_cost.py`:
```python
"""cost: rate resolution, estimate math, label/dialog wording."""

from __future__ import annotations

import pytest

from app import config
from app.core import llm
from app.core.llm import cost

ANTH = llm.PRESETS["anthropic"]
OLLAMA = llm.PRESETS["ollama"]
CUSTOM = llm.PRESETS["custom"]


def test_rates_for_cloud_default():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    assert (r.input_per_mtok, r.output_per_mtok) == (2.0, 10.0)
    assert r.known and not r.free


def test_rates_for_cloud_override():
    r = cost.rates_for(ANTH, {"llm_rates": {"anthropic": [3.0, 15.0]}})
    assert (r.input_per_mtok, r.output_per_mtok) == (3.0, 15.0)
    assert r.known


def test_rates_for_local_is_free():
    r = cost.rates_for(OLLAMA, {"llm_rates": {"ollama": [9.0, 9.0]}})  # override ignored
    assert r.free and r.known
    assert (r.input_per_mtok, r.output_per_mtok) == (0.0, 0.0)


def test_rates_for_custom_unknown_until_set():
    assert cost.rates_for(CUSTOM, {"llm_rates": {}}).known is False
    r = cost.rates_for(CUSTOM, {"llm_rates": {"custom": [1.0, 2.0]}})
    assert r.known and (r.input_per_mtok, r.output_per_mtok) == (1.0, 2.0)


@pytest.mark.parametrize(
    "bad",
    ["3,15", [3.0], [-1.0, 2.0], ["a", "b"], None, {"in": 3}, [3.0, 15.0, 1.0]],
)
def test_rates_for_ignores_bad_override_shapes(bad):
    r = cost.rates_for(ANTH, {"llm_rates": {"anthropic": bad}})
    assert (r.input_per_mtok, r.output_per_mtok) == (2.0, 10.0)
    r2 = cost.rates_for(ANTH, {"llm_rates": "not a dict"})
    assert (r2.input_per_mtok, r2.output_per_mtok) == (2.0, 10.0)


def test_rates_for_reads_config_when_cfg_omitted():
    cfg = config.load_config()
    cfg["llm_rates"] = {"anthropic": [4.0, 20.0]}
    config.save_config(cfg)
    assert cost.rates_for(ANTH).input_per_mtok == 4.0


def test_estimate_math_and_ceil():
    r = cost.Rates(2.0, 10.0, known=True, free=False)
    e = cost.estimate(total_chars=150_001, num_parts=2, rates=r)
    assert e.input_tokens == 37_501  # ceil(150001/4)
    assert e.output_tokens_upper == 8_000
    assert e.num_parts == 2
    assert e.cost_upper == pytest.approx(37_501 / 1e6 * 2.0 + 8_000 / 1e6 * 10.0)
    assert not e.free


def test_estimate_zero_parts_is_zero():
    r = cost.Rates(2.0, 10.0, known=True, free=False)
    e = cost.estimate(0, 0, r)
    assert (e.input_tokens, e.output_tokens_upper, e.cost_upper) == (0, 0, 0.0)


def test_estimate_free_and_unknown():
    free = cost.estimate(1000, 1, cost.Rates(0, 0, known=True, free=True))
    assert free.free and free.cost_upper == 0.0
    unk = cost.estimate(1000, 1, cost.Rates(0, 0, known=False, free=False))
    assert unk.cost_upper is None


@pytest.mark.parametrize("n, s", [(0, "~0"), (999, "~999"), (1000, "~1k"), (37_501, "~38k"), (1_250_000, "~1250k")])
def test_fmt_tokens(n, s):
    assert cost.fmt_tokens(n) == s


@pytest.mark.parametrize("x, s", [(0.0, "$0.00"), (0.004, "<$0.01"), (0.01, "$0.01"), (0.155, "$0.16"), (12.5, "$12.50")])
def test_fmt_dollars(x, s):
    assert cost.fmt_dollars(x) == s


@pytest.mark.parametrize("x, s", [(2.0, "2"), (10.0, "10"), (0.30, "0.3"), (2.5, "2.5"), (0.075, "0.075")])
def test_fmt_rate(x, s):
    assert cost.fmt_rate(x) == s


def test_format_line_no_files():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    assert cost.format_line(cost.estimate(0, 0, r), ANTH, r) == "Add transcript files to see an estimate."


def test_format_line_known():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    e = cost.estimate(150_001, 2, r)
    assert cost.format_line(e, ANTH, r) == (
        "Estimate: ~38k input tokens · up to ~8k output · est. up to ~$0.16 "
        "(Claude @ $2/$10 per M) · + one more call when you consolidate"
    )


def test_format_line_free():
    r = cost.rates_for(OLLAMA, {"llm_rates": {}})
    e = cost.estimate(150_001, 2, r)
    assert cost.format_line(e, OLLAMA, r) == (
        "Estimate: ~38k input tokens · up to ~8k output · Free · local compute (Ollama (local))"
    )


def test_format_line_unknown():
    r = cost.rates_for(CUSTOM, {"llm_rates": {}})
    e = cost.estimate(150_001, 2, r)
    assert cost.format_line(e, CUSTOM, r) == (
        "Estimate: ~38k input tokens · up to ~8k output · cost unknown — "
        "set Custom endpoint rates in Settings (⚙)"
    )


def test_format_sub_cent():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    e = cost.estimate(400, 1, r, max_output_tokens=10)  # 100 in + 10 out tokens
    assert e.cost_upper is not None and 0 < e.cost_upper < 0.01
    assert "est. up to ~<$0.01" in cost.format_line(e, ANTH, r)


def test_format_confirm():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    e = cost.estimate(150_001, 2, r)
    assert cost.format_confirm(e, ANTH, r) == (
        "This will send ~38k input tokens to Claude and generate up to ~8k output tokens "
        "across 2 part(s).\nEstimated cost: up to ~$0.16 (approximate, at your configured rates)."
        "\n\nContinue?"
    )
```

Append to `tests/unit/test_llm_factory.py`:
```python
def test_preset_rate_defaults():
    expect = {
        "anthropic": (2.0, 10.0),
        "gemini": (0.30, 2.50),
        "openrouter": (2.0, 10.0),
        "ollama": (0.0, 0.0),
        "lmstudio": (0.0, 0.0),
        "custom": (0.0, 0.0),
    }
    for pid, (i, o) in expect.items():
        p = llm.PRESETS[pid]
        assert (p.input_per_mtok, p.output_per_mtok) == (i, o), pid
```
In `tests/unit/test_config_llm.py::test_new_llm_defaults_merge_into_old_config_json` append `assert cfg["llm_rates"] == {}`, and add:
```python
def test_llm_rates_round_trip():
    cfg = config.load_config()
    cfg["llm_rates"] = {"anthropic": [3.0, 15.0]}
    config.save_config(cfg)
    assert config.load_config()["llm_rates"] == {"anthropic": [3.0, 15.0]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_cost.py tests/unit/test_llm_factory.py tests/unit/test_config_llm.py -v`
Expected: FAIL with `ImportError: cannot import name 'cost'`, `AttributeError: 'Preset' object has no attribute 'input_per_mtok'`, `KeyError: 'llm_rates'`.

- [ ] **Step 3: Preset fields and config key**

In `app/core/llm/factory.py` add to the `Preset` dataclass after `local_runtime: str = ""`:
```python
    input_per_mtok: float = 0.0  # default $ per million input tokens for default_model (0 = unknown/free)
    output_per_mtok: float = 0.0
```
Add `input_per_mtok=2.0, output_per_mtok=10.0` to the `anthropic` and `openrouter` presets, `input_per_mtok=0.30, output_per_mtok=2.50` to `gemini`; leave the three others at the defaults.

In `app/config.py` `DEFAULT_CONFIG`, after `"llm_base_url_custom": "",` add:
```python
    "llm_rates": {},  # {provider_id: [input_$_per_M, output_$_per_M]} user overrides; blank = preset default
```

- [ ] **Step 4: Implement `cost.py`**

Create `app/core/llm/cost.py`:
```python
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
        return Estimate(0, 0, max(num_parts, 0), 0.0 if (rates.known or rates.free) else None, rates.free)
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
    return f"${x:.2f}"


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
```
In `app/core/llm/__init__.py` add `from app.core.llm import cost` next to the `local_detect` import and `"cost"` to `__all__`.

- [ ] **Step 5: Run tests, then the whole suite**

Run: `.venv\Scripts\python -m pytest tests/unit/test_llm_cost.py tests/unit/test_llm_factory.py tests/unit/test_config_llm.py -v` → all PASS. If `test_fmt_tokens[1250000]` or a rounding case differs, fix the formatter, not the test.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 6: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/core/llm/cost.py app/core/llm/factory.py app/core/llm/__init__.py app/config.py tests/unit/test_llm_cost.py tests/unit/test_llm_factory.py tests/unit/test_config_llm.py
git commit -m "feat(llm): cost module (rates, estimate, wording), preset rate defaults, llm_rates config key"
```

---

### Task 2: Settings — per-provider rate row

**Files:**
- Modify: `app/ui/settings_dialog.py` (`_build_llm_section` state seeding + a new row after the badge row; `_stash_llm_fields`, `_load_llm_fields`, `_save`; new `_reset_rates`)
- Test: `tests/gui/test_settings_llm.py` (five tests)

**Interfaces:**
- Consumes: `llm.PRESETS[pid].input_per_mtok/output_per_mtok`, `llm.PRESETS[pid].local_runtime`, config `llm_rates`.
- Produces: `llm_rates_row` (ttk.Frame), `llm_rate_in_var`, `llm_rate_out_var` (tk.StringVar), `_reset_rates()`, per-provider state keys `rate_in`, `rate_out` (strings).

- [ ] **Step 1: Write the failing GUI tests**

Append to `tests/gui/test_settings_llm.py`:
```python
def test_rate_row_defaults_and_hidden_for_local(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        assert dlg.llm_rates_row.winfo_manager() == "grid"
        assert dlg.llm_rate_in_var.get() == "2" and dlg.llm_rate_out_var.get() == "10"
        _select(dlg, "Google Gemini")
        assert dlg.llm_rate_in_var.get() == "0.3" and dlg.llm_rate_out_var.get() == "2.5"
        _select(dlg, "Ollama (local)")
        assert dlg.llm_rates_row.winfo_manager() == ""
        _select(dlg, "Custom endpoint")
        assert dlg.llm_rates_row.winfo_manager() == "grid"
        assert dlg.llm_rate_in_var.get() == "0" and dlg.llm_rate_out_var.get() == "0"
    finally:
        dlg.destroy()


def test_rate_override_persists_and_survives_switch(root):
    dlg = _open(root)
    dlg.llm_rate_in_var.set("3")
    dlg.llm_rate_out_var.set("15")
    _select(dlg, "Google Gemini")
    _select(dlg, "Claude")
    assert dlg.llm_rate_in_var.get() == "3" and dlg.llm_rate_out_var.get() == "15"
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_rates"] == {"anthropic": [3.0, 15.0]}
    dlg = _open(root)
    try:
        assert dlg.llm_rate_in_var.get() == "3" and dlg.llm_rate_out_var.get() == "15"
    finally:
        dlg.destroy()


def test_default_rates_remove_override(root):
    cfg = config.load_config()
    cfg["llm_rates"] = {"anthropic": [3.0, 15.0]}
    config.save_config(cfg)
    dlg = _open(root)
    assert dlg.llm_rate_in_var.get() == "3"
    dlg._reset_rates()
    assert dlg.llm_rate_in_var.get() == "2" and dlg.llm_rate_out_var.get() == "10"
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_rates"] == {}


@pytest.mark.parametrize("bad_in, bad_out", [("2,5", "10"), ("$2", "10"), ("", "10"), ("abc", "xyz"), ("-1", "10")])
def test_bad_rate_text_drops_override(root, bad_in, bad_out):
    dlg = _open(root)
    dlg.llm_rate_in_var.set(bad_in)
    dlg.llm_rate_out_var.set(bad_out)
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert "anthropic" not in config.load_config()["llm_rates"]


def test_rate_override_for_custom_makes_rates_known(root):
    dlg = _open(root)
    _select(dlg, "Custom endpoint")
    dlg.llm_rate_in_var.set("1")
    dlg.llm_rate_out_var.set("2")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_rates"] == {"custom": [1.0, 2.0]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py -v -k rate`
Expected: FAIL with `AttributeError: 'SettingsDialog' object has no attribute 'llm_rates_row'`.

- [ ] **Step 3: Implement**

In `app/ui/settings_dialog.py`:

Import: add `from app.core.llm import cost, local_detect` (replacing the existing `local_detect` import line).

State seeding in `_build_llm_section` — inside the loop, after `"caveat": "",` add:
```python
                "rate_in": "",
                "rate_out": "",
```
and right after the loop (before `self._detect_queue = ...`):
```python
        for pid, preset in llm.PRESETS.items():
            r = cost.rates_for(preset, cfg)
            self._llm_state[pid]["rate_in"] = cost.fmt_rate(r.input_per_mtok)
            self._llm_state[pid]["rate_out"] = cost.fmt_rate(r.output_per_mtok)
```

After the badge row (`self.llm_badge_label.grid(...)` / `row += 1`) insert:
```python
        self.llm_rates_row = ttk.Frame(self)
        self.llm_rates_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_rates_row, text="Rates ($ per M tokens):").grid(
            row=0, column=0, sticky="w", **pad
        )
        rates_inner = ttk.Frame(self.llm_rates_row)
        rates_inner.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(rates_inner, text="in").pack(side="left")
        self.llm_rate_in_var = tk.StringVar()
        ttk.Entry(rates_inner, textvariable=self.llm_rate_in_var, width=8).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(rates_inner, text="out").pack(side="left")
        self.llm_rate_out_var = tk.StringVar()
        ttk.Entry(rates_inner, textvariable=self.llm_rate_out_var, width=8).pack(
            side="left", padx=(4, 12)
        )
        ttk.Button(rates_inner, text="Default", command=self._reset_rates).pack(side="left")
        row += 1
```

`_stash_llm_fields`: add
```python
        st["rate_in"] = self.llm_rate_in_var.get()
        st["rate_out"] = self.llm_rate_out_var.get()
```
`_load_llm_fields`: after `self.llm_base_url_var.set(st["base_url"])` add
```python
        self.llm_rate_in_var.set(st["rate_in"])
        self.llm_rate_out_var.set(st["rate_out"])
        if preset.local_runtime:
            self.llm_rates_row.grid_remove()
        else:
            self.llm_rates_row.grid()
```
New method (next to `_reset_model`):
```python
    def _reset_rates(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        self.llm_rate_in_var.set(cost.fmt_rate(preset.input_per_mtok))
        self.llm_rate_out_var.set(cost.fmt_rate(preset.output_per_mtok))
```
`_save`: after the `llm_model_*` loop add
```python
            rates = dict(cfg.get("llm_rates") or {}) if isinstance(cfg.get("llm_rates"), dict) else {}
            for pid, st in self._llm_state.items():
                preset = llm.PRESETS[pid]
                if preset.local_runtime:
                    rates.pop(pid, None)
                    continue
                pair = self._parse_rates(st["rate_in"], st["rate_out"])
                if pair is None or pair == (preset.input_per_mtok, preset.output_per_mtok):
                    rates.pop(pid, None)
                else:
                    rates[pid] = [pair[0], pair[1]]
            cfg["llm_rates"] = rates
```
and the helper (static, next to `_reset_rates`):
```python
    @staticmethod
    def _parse_rates(text_in: str, text_out: str) -> tuple[float, float] | None:
        try:
            i, o = float(text_in.strip()), float(text_out.strip())
        except ValueError:
            return None
        if i < 0 or o < 0:
            return None
        return i, o
```
Note `float("2,5")` and `float("$2")` raise `ValueError` → `None` → override dropped (Review Focus 4). `float("")` also raises.

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_settings_llm.py tests/gui/test_settings_discovery.py tests/gui/test_settings_crash_reporting.py -v` → all PASS.
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/ui/settings_dialog.py tests/gui/test_settings_llm.py
git commit -m "feat(settings): per-provider rate row ($ per M tokens) with default reset; overrides stored in llm_rates"
```

---

### Task 3: Summarize tab — estimate label, recompute hooks, confirm gate

**Files:**
- Modify: `app/ui/summarize_tab.py` (imports; grid rows 6–8 → 7–9; new label at row 6; `_refresh_estimate`; hooks in `__init__`, `_add_files`, `_remove_files`, `_clear_files`, `_on_prompt_select`, `load_session`, `on_settings_changed`; gate in `_start`)
- Test: `tests/gui/test_summarize_cost.py` (new)

**Interfaces:**
- Consumes: `cost.rates_for`, `cost.estimate`, `cost.format_line`, `cost.format_confirm`, `cost.CONTEXT_ALLOWANCE_CHARS`, `llm.active_preset()`.
- Produces: `SummarizeTab.estimate_var` (tk.StringVar), `SummarizeTab._refresh_estimate()`, `SummarizeTab._current_estimate() -> tuple[Estimate, Preset, Rates]`.

- [ ] **Step 1: Write the failing GUI tests**

Create `tests/gui/test_summarize_cost.py`:
```python
"""Summarize tab: live cost estimate line and the confirm-cost gate at Start."""

from __future__ import annotations

import threading
import tkinter as tk
import types

import pytest

from app import config
from app.core import library, speakers_io
from app.data import db

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


def _tab(root):
    db.init_db()
    from app.ui.summarize_tab import SummarizeTab

    tab = SummarizeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    return tab


def _transcript(tmp_path, name="t1.txt", chars=150_000):
    p = tmp_path / name
    p.write_text("x" * chars, encoding="utf-8")
    return str(p)


def _add(tab, path):
    tab.transcript_files.append(path)
    tab.files_box.insert("end", path)
    tab._refresh_estimate()


def test_label_empty_state_and_known_estimate(root, tmp_path):
    tab = _tab(root)
    assert tab.estimate_var.get() == "Add transcript files to see an estimate."
    _add(tab, _transcript(tmp_path))
    text = tab.estimate_var.get()
    assert text.startswith("Estimate: ~")  # ~38k-40k depending on the default prompt length
    assert "input tokens · up to ~4k output · est. up to ~$" in text
    assert "(Claude @ $2/$10 per M)" in text and "consolidate" in text


def test_label_updates_on_clear_and_settings_change(root, tmp_path):
    tab = _tab(root)
    _add(tab, _transcript(tmp_path))
    tab._clear_files()
    assert tab.estimate_var.get() == "Add transcript files to see an estimate."
    _add(tab, _transcript(tmp_path))
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    tab.on_settings_changed()
    assert tab.estimate_var.get().endswith("· Free · local compute (Ollama (local))")
    cfg["llm_provider"] = "anthropic"
    cfg["llm_rates"] = {"anthropic": [4.0, 20.0]}
    config.save_config(cfg)
    tab.on_settings_changed()
    assert "(Claude @ $4/$20 per M)" in tab.estimate_var.get()


def test_estimate_skips_missing_files(root, tmp_path):
    tab = _tab(root)
    gone = str(tmp_path / "gone.txt")
    tab.transcript_files.append(gone)
    tab.files_box.insert("end", gone)
    tab._refresh_estimate()  # must not raise
    text = tab.estimate_var.get()
    assert text.startswith("Estimate: ~") and "input tokens · up to ~4k output" in text


def _arm_start(tab, tmp_path, monkeypatch, provider="anthropic"):
    slug = library.create_campaign("Strahd")
    library.add_version(slug, speakers_io.profiles_to_speakers_doc("Strahd", "", []))
    tab.speakers_path = str(library.current_version_path(slug))
    _add(tab, _transcript(tmp_path))
    tab.out_var.set(str(tmp_path / "out"))
    cfg = config.load_config()
    cfg["llm_provider"] = provider
    if provider == "ollama":
        cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    if provider == "anthropic":
        config.save_provider_key("anthropic", "k")
    started = []

    class _Thread:
        def __init__(self, *a, **k):
            started.append(k.get("target"))

        def start(self):
            pass

    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.threading, "Thread", _Thread)
    return started


def test_start_confirm_no_aborts_yes_proceeds(root, tmp_path, monkeypatch):
    tab = _tab(root)
    started = _arm_start(tab, tmp_path, monkeypatch)
    asked = []
    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.messagebox, "askyesno", lambda title, msg, **k: (asked.append((title, msg)), False)[1])
    tab._start()
    assert asked and asked[0][0] == "Confirm cost" and "Continue?" in asked[0][1]
    assert started == [] and not tab._busy
    monkeypatch.setattr(st.messagebox, "askyesno", lambda title, msg, **k: True)
    tab._start()
    assert len(started) == 1


def test_start_on_local_never_prompts(root, tmp_path, monkeypatch):
    tab = _tab(root)
    started = _arm_start(tab, tmp_path, monkeypatch, provider="ollama")
    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.messagebox, "askyesno", lambda *a, **k: pytest.fail("must not prompt"))
    tab._start()
    assert len(started) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/gui/test_summarize_cost.py -v`
Expected: FAIL with `AttributeError: 'SummarizeTab' object has no attribute 'estimate_var'`.

- [ ] **Step 3: Implement**

In `app/ui/summarize_tab.py`:

Import: change `from app.core import library, llm, privacy, speakers_io, summarizer` to also import cost: add a line `from app.core.llm import cost`.

Grid reflow in `__init__`: change `self.go_btn.grid(row=6, ...)` → `row=7`; `self.cancel_btn.grid(row=7, ...)` → `row=8`; the status label `.grid(row=7, ...)` → `row=8`; `out_frame.grid(row=8, ...)` → `row=9`. Insert before the `self.go_btn = ttk.Button(` line:
```python
        self.estimate_var = tk.StringVar(value="")
        ttk.Label(
            body, textvariable=self.estimate_var, style=LBL_DIM, wraplength=760, justify="left"
        ).grid(row=6, column=0, columnspan=4, sticky="w", **pad)
```
At the end of `__init__` (after `self._privacy_note = add_privacy_note(...)`) add `self._refresh_estimate()`.

New methods (place after `on_show`):
```python
    # ---- cost estimate ----
    def _current_estimate(self):
        total = cost.CONTEXT_ALLOWANCE_CHARS
        for p in self.transcript_files:
            try:
                total += os.path.getsize(p)
            except OSError:
                continue  # file vanished since it was added; the run reports it
        idx = self.prompt_combo.current()
        if 0 <= idx < len(self._prompt_options):
            total += len(self._prompt_options[idx].get("content", ""))
        preset = llm.active_preset()
        rates = cost.rates_for(preset)
        est = cost.estimate(total, len(self.transcript_files), rates)
        return est, preset, rates

    def _refresh_estimate(self) -> None:
        est, preset, rates = self._current_estimate()
        self.estimate_var.set(cost.format_line(est, preset, rates))
```
Hooks: append `self._refresh_estimate()` as the last statement of `_add_files`, `_remove_files`, `_clear_files`, `_on_prompt_select`, `load_session`, and `on_settings_changed`.

Gate in `_start`: immediately after the output-folder validation (`if not out: ... return`) and before `Path(out).mkdir(...)`, insert:
```python
        est, preset, rates = self._current_estimate()
        if est.cost_upper is not None and est.cost_upper > 0:
            if not messagebox.askyesno("Confirm cost", cost.format_confirm(est, preset, rates)):
                return
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/gui/test_summarize_cost.py tests/gui/test_summarize_npcs_wiring.py tests/gui/test_stage_tabs_session.py tests/gui/test_llm_preflight.py tests/smoke/test_privacy_dialog.py -v` → all PASS. (`test_estimate_skips_missing_files` only checks for a non-empty estimate with the 4k output bound — the point is no crash.)
Run: `.venv\Scripts\python -m pytest -q` → all PASS.

- [ ] **Step 5: Lint and commit**

```
.venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
git add app/ui/summarize_tab.py tests/gui/test_summarize_cost.py
git commit -m "feat(summarize): live cost estimate above Start and a confirm-cost gate for paid runs"
```

---

### Task 4: README note and the full gate

**Files:**
- Modify: `README.md` (Layout → Summarize bullet; Settings bullet)

- [ ] **Step 1: README**

In "Layout" → the **Summarize** bullet, append the sentence: `An estimate line above Start shows the approximate input size, the output upper bound, and the cost at your configured rates (free for local models); paid runs ask for confirmation first.`
In the Settings bullet, after "model and API key" add ", per-provider rates".

- [ ] **Step 2: Full gate**

```
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m bandit -q -r app -ll
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -m "not gui" -q
```
Expected: all clean/green (≈ 368 + 23 + 1 + 1 + 1 + 5 + 6 ≈ 405 full).

- [ ] **Step 3: Commit and hand back**

```
git add README.md
git commit -m "docs: README notes the Summarize cost estimate and per-provider rates"
```
Report commits and counts. The controller does the manual check from `run_dev.bat` (open Summarize, add a transcript, read the line; press Start on Claude and cancel the dialog) and opens the PR with `Roadmap: Imagination-Industries-LLC/CampaignScribe-planning#10`.
