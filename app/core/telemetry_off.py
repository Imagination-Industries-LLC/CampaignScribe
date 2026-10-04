"""Disable third-party usage telemetry before any ML library is imported (Tk-free).

pyannote.audio 4.x reports pipeline usage to otel.pyannote.ai unless
PYANNOTE_METRICS_ENABLED is set before it is imported. CampaignScribe sends no
usage data, so both switches default to off. A user who explicitly sets either
variable in their environment keeps their choice.
"""

from __future__ import annotations

import os

_DEFAULTS = {
    "PYANNOTE_METRICS_ENABLED": "false",  # pyannote.audio telemetry
    "OTEL_SDK_DISABLED": "true",  # OpenTelemetry SDK (pyannote's exporter) becomes a no-op
}


def apply() -> None:
    for key, value in _DEFAULTS.items():
        os.environ.setdefault(key, value)


apply()
