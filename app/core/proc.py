"""Subprocess helpers shared across the app."""

from __future__ import annotations

import subprocess

# Launching a console subprocess (nvidia-smi, explorer, ...) on Windows briefly
# flashes a console window. CREATE_NO_WINDOW suppresses it. The flag only exists
# on Windows, so fall back to 0 (a harmless no-op) elsewhere — this lets every
# subprocess call pass creationflags=CREATE_NO_WINDOW uniformly while staying
# cross-platform safe (creationflags=0 is the default on POSIX).
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
