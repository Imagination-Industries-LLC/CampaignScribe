"""Auto-stop line formatting for the Discord record dialog."""

from __future__ import annotations

import pytest

from app.core import autostop


@pytest.mark.parametrize(
    "elapsed, limit, text, style",
    [
        (0, 360, "\u23f1 Auto-stop at 6:00 \u2014 in 6:00:00", "normal"),
        (3600 + 59, 90, "\u23f1 Auto-stop at 1:30 \u2014 in 0:29:01", "normal"),
        (360 * 60 - 299, 360, "\u23f1 Auto-stop in 4:59", "warn"),
        (360 * 60 - 300, 360, "\u23f1 Auto-stop in 5:00", "warn"),
        (360 * 60 - 301, 360, "\u23f1 Auto-stop at 6:00 \u2014 in 0:05:01", "normal"),
        (
            360 * 60,
            360,
            "\u23f1 Past the maximum length \u2014 auto-stop is off until you set a longer limit",
            "error",
        ),
        (
            400 * 60,
            360,
            "\u23f1 Past the maximum length \u2014 auto-stop is off until you set a longer limit",
            "error",
        ),
    ],
)
def test_autostop_text(elapsed, limit, text, style):
    assert autostop.autostop_text(elapsed, limit) == (text, style)


def test_formatters():
    assert autostop.fmt_hm(90) == "1:30"
    assert autostop.fmt_hms(3661) == "1:01:01"
