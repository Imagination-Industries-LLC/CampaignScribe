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
    [
        "3,15",
        [3.0],
        [-1.0, 2.0],
        ["a", "b"],
        None,
        {"in": 3},
        [3.0, 15.0, 1.0],
        [float("inf"), 1.0],
        [1.0, float("nan")],
    ],
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


@pytest.mark.parametrize(
    "n, s", [(0, "~0"), (999, "~999"), (1000, "~1k"), (37_501, "~38k"), (1_250_000, "~1250k")]
)
def test_fmt_tokens(n, s):
    assert cost.fmt_tokens(n) == s


@pytest.mark.parametrize(
    "x, s", [(0.0, "$0.00"), (0.004, "<$0.01"), (0.01, "$0.01"), (0.155, "$0.16"), (12.5, "$12.50")]
)
def test_fmt_dollars(x, s):
    assert cost.fmt_dollars(x) == s


@pytest.mark.parametrize(
    "x, s", [(2.0, "2"), (10.0, "10"), (0.30, "0.3"), (2.5, "2.5"), (0.075, "0.075")]
)
def test_fmt_rate(x, s):
    assert cost.fmt_rate(x) == s


def test_format_line_no_files():
    r = cost.rates_for(ANTH, {"llm_rates": {}})
    assert (
        cost.format_line(cost.estimate(0, 0, r), ANTH, r)
        == "Add transcript files to see an estimate."
    )


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


def test_fmt_dollars_non_finite_never_raises():
    assert cost.fmt_dollars(float("inf")) == "$?"
    assert cost.fmt_dollars(float("nan")) == "$?"
