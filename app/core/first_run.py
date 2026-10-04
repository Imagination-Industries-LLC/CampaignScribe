"""First-launch setup offer (Tk-free).

The welcome is offered once per install, and only while the active AI provider
is not ready. The flag is set when the welcome is shown, whatever the user picks.
"""

from __future__ import annotations

from typing import Any

from app import config
from app.core import llm

SETUP_OFFERED_KEY = "setup_welcome_shown"


def should_offer_setup(cfg: dict[str, Any]) -> bool:
    """True when the welcome has never been shown and the active provider is not ready."""
    return not cfg.get(SETUP_OFFERED_KEY, False) and not llm.provider_ready(cfg)


def mark_setup_offered() -> None:
    """Persist the flag. Reload first so a concurrent write is not clobbered."""
    cfg = config.load_config()
    cfg[SETUP_OFFERED_KEY] = True
    config.save_config(cfg)
