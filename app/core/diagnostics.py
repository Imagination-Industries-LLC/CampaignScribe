"""User-initiated diagnostics bundle for the Feedback & Support hub.

Builds a single scrubbed, non-sensitive plain-text block (version / OS / GPU,
optionally the tail of errors.log). Deliberately excludes transcripts, audio,
API keys/tokens, and speakers.json. Tk-free.
"""

from __future__ import annotations

import os
import platform
import re

from app import __version__, config

LOG_TAIL_LINES = 200


def scrub(text: str) -> str:
    """Defense-in-depth PII scrub: user home -> ~, drop email addresses.

    UNC paths (\\\\server\\...) are not scrubbed.
    """
    if not text:
        return text
    out = text
    # Replace the real user home and any C:\Users\<name> style paths with ~.
    home = os.path.expanduser("~")
    if home and home != "~":
        out = out.replace(home, "~")
    # Fallback path scrub (defense-in-depth on the log tail). Match up to the next
    # path separator so usernames containing spaces are fully removed; IGNORECASE
    # because Windows paths are case-insensitive. Over-scrubbing is safe; leaking is not.
    out = re.sub(r"[A-Za-z]:\\Users\\[^\\/]+", "~", out, flags=re.IGNORECASE)
    out = re.sub(r"/home/[^/]+", "~", out)
    # Drop email addresses.
    out = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email removed]", out)
    # Redact API keys/tokens (Anthropic sk-..., HuggingFace hf_...).
    out = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[token removed]", out)
    out = re.sub(r"\bhf_[A-Za-z0-9]{8,}", "[token removed]", out)
    return out


def _gpu_state() -> str:
    """One-line GPU/torch summary from transcriber.check_gpu() (best-effort)."""
    try:
        from app.core.transcriber import check_gpu

        g = check_gpu()
        if g.get("cuda_available"):
            return f"GPU: {g.get('device_name')} ({g.get('vram_gb')} GB) · torch {g.get('torch_version')} · CUDA {g.get('torch_cuda_version')}"
        return f"GPU: none/CPU ({g.get('recommendation')}) · torch {g.get('torch_version')}"
    except Exception:
        return "GPU: unavailable"


def _log_tail() -> str:
    try:
        path = config.get_error_log_path()
        if not path.exists():
            return "(no errors.log)"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-LOG_TAIL_LINES:]
        return "\n".join(tail) if tail else "(errors.log is empty)"
    except Exception as e:  # noqa: BLE001 - diagnostics must never crash the app
        return f"(could not read errors.log: {e})"


def _header_lines() -> list[str]:
    return [
        f"CampaignScribe {__version__}",
        f"OS: {platform.platform()}",
        f"Python: {platform.python_version()}",
        _gpu_state(),
    ]


def build_email_header() -> str:
    """Compact, log-free build-info header for the mailto: body (length-limited)."""
    return scrub("\n".join(_header_lines()))


def build_diagnostics_bundle(include_log_tail: bool = True) -> str:
    """Full diagnostics block for Copy Diagnostics / Report a Problem."""
    parts = list(_header_lines())
    if include_log_tail:
        parts.append("")
        parts.append("--- errors.log (tail) ---")
        parts.append(_log_tail())
    return scrub("\n".join(parts))
