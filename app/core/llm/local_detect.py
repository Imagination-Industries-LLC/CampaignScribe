"""Probe local OpenAI-compatible runtimes (Ollama, LM Studio) and list their models.

Pure urllib with a short timeout; a stopped runtime is a result, not an
exception. Tk-free; no SDK import. Settings runs this on a worker thread.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

RUNTIMES: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}
RUNTIME_NAMES: dict[str, str] = {"ollama": "Ollama", "lmstudio": "LM Studio"}

_DEFAULT_TIMEOUT_S = 1.5
QUALITY_GOOD_MIN_B = 12.0
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[bB]")


@dataclass(frozen=True)
class LocalModel:
    model_id: str
    parameter_size: str = ""  # "14.8B" when the runtime reports it, else ""


@dataclass(frozen=True)
class DetectResult:
    runtime_id: str
    running: bool
    models: list[LocalModel] = field(default_factory=list)
    error: str = ""  # "" when running; otherwise a one-line reason


def quality_label(parameter_size: str) -> str:
    """'Good' at or above QUALITY_GOOD_MIN_B billion parameters, else 'Basic'."""
    m = _SIZE_RE.match(parameter_size or "")
    if not m:
        return "Basic"
    return "Good" if float(m.group(1)) >= QUALITY_GOOD_MIN_B else "Basic"


def _get_json(url: str, timeout_s: float):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - localhost only
        return json.loads(resp.read().decode("utf-8"))


def detect(
    runtime_id: str, *, base_url: str | None = None, timeout_s: float = _DEFAULT_TIMEOUT_S
) -> DetectResult:
    """Probe one runtime. Never raises for network/format problems."""
    if runtime_id not in RUNTIMES:
        raise ValueError(f"unknown local runtime: {runtime_id!r}")
    base = (base_url or RUNTIMES[runtime_id]).rstrip("/")
    try:
        if runtime_id == "ollama":
            root = base[: -len("/v1")] if base.endswith("/v1") else base
            data = _get_json(f"{root}/api/tags", timeout_s)
            models = [
                LocalModel(
                    str(m.get("name") or m.get("model") or ""),
                    str((m.get("details") or {}).get("parameter_size") or ""),
                )
                for m in data["models"]
            ]
        else:
            data = _get_json(f"{base}/models", timeout_s)
            models = [LocalModel(str(m.get("id") or "")) for m in data["data"]]
        models = [m for m in models if m.model_id]
        return DetectResult(runtime_id, True, models)
    except urllib.error.HTTPError as e:
        return DetectResult(runtime_id, False, [], f"HTTPError: {e.code}")
    except (urllib.error.URLError, OSError) as e:  # refused, timeout, DNS
        reason = getattr(e, "reason", None) or e
        return DetectResult(runtime_id, False, [], f"{type(e).__name__}: {reason}")
    except (
        ValueError,
        KeyError,
        AttributeError,
        TypeError,
        http.client.HTTPException,
    ) as e:  # bad JSON / wrong shape / protocol error
        return DetectResult(runtime_id, False, [], f"unexpected response: {type(e).__name__}: {e}")
