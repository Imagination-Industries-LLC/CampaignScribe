"""Resolve where the app's bundled (read-only) files live.

Three layouts, checked in this order:

* installed - the per-user installer's launcher sets ``CAMPAIGNSCRIBE_HOME`` to
  the install dir; honoured only if ``<home>/main.py`` exists, so a stale
  variable can never break a dev checkout.
* frozen - PyInstaller bundle (``sys._MEIPASS``).
* dev - the repo root (parent of ``app/``).

This module deliberately offers no writable-location helper: user data lives
under ``app.config.get_app_data_dir()``, never under ``app_home()``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOME_ENV = "CAMPAIGNSCRIBE_HOME"


def _installed_home() -> Path | None:
    raw = os.environ.get(HOME_ENV)
    if not raw:
        return None
    home = Path(raw)
    return home if (home / "main.py").is_file() else None


def mode() -> str:
    """Return ``"installed"``, ``"frozen"`` or ``"dev"``."""
    if _installed_home() is not None:
        return "installed"
    if getattr(sys, "frozen", False):
        return "frozen"
    return "dev"


def app_home() -> Path:
    """Root directory holding ``assets/``, ``models/``, ``ffmpeg/`` etc."""
    home = _installed_home()
    if home is not None:
        return home
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]
