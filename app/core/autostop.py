"""Auto-stop line text for the Discord record dialog (Tk-free, unit-testable)."""

from __future__ import annotations

import math

WARN_WINDOW_S = 300
PAST_LIMIT_TEXT = "⏱ Past the maximum length — auto-stop is off until you set a longer limit"


def fmt_hm(minutes: int) -> str:
    """Minutes -> H:MM."""
    minutes = max(0, int(minutes))
    return f"{minutes // 60}:{minutes % 60:02d}"


def fmt_hms(seconds: float) -> str:
    """Seconds -> H:MM:SS."""
    s = max(0, int(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def autostop_text(elapsed_s: float, limit_min: int) -> tuple[str, str]:
    """Return (text, style) for the auto-stop line; style is normal | warn | error."""
    remaining = limit_min * 60 - elapsed_s
    if remaining <= 0:
        return PAST_LIMIT_TEXT, "error"
    left = math.ceil(remaining)
    if left <= WARN_WINDOW_S:
        return f"⏱ Auto-stop in {left // 60}:{left % 60:02d}", "warn"
    return f"⏱ Auto-stop at {fmt_hm(limit_min)} — in {fmt_hms(left)}", "normal"
