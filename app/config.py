"""App-wide configuration: paths, settings, and keyring-backed secrets."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import keyring

SERVICE_NAME = "CampaignScribe"

DEFAULT_CONFIG: dict[str, Any] = {
    "default_output_folder": "",
    "default_whisper_model": "large-v3",
    "default_num_speakers": 5,
    "theme_mode": "dark",
    "last_speakers_json": "",
    "last_campaign": "",
    "library_import_prompted": False,
    "sessions_backlinked": False,
    "last_output_folder": "",
    "last_audio_dir": "",
    "last_json_dir": "",
    "window_width": 1000,
    "window_height": 760,
    "window_x": -1,
    "window_y": -1,
    "discover_sample_minutes": 0,  # 0 = discover on the full (first) audio file; >0 caps to N minutes
    "discover_whisper_model": "small",  # lighter model used only during speaker discovery
    "voice_match_enabled": True,
    "voice_match_threshold": 0.70,  # cosine; below -> cluster stays manual
    "summaries_completed": 0,  # count of completed consolidated summaries (drives the one-time support nudge)
    "support_nudge_shown": False,  # the gentle one-time support nudge has been shown
    "setup_welcome_shown": False,  # first-launch welcome (pick an AI provider) has been offered
    "crash_reporting_enabled": False,  # opt-in (default off) Sentry crash reporting
    # ---- LLM provider (Multi-Provider LLM, Phase 2) ----
    "llm_provider": "anthropic",  # one of app.core.llm.PRESETS
    "llm_model_anthropic": "claude-sonnet-5-5",
    "llm_model_gemini": "gemini-2.5-flash",
    "llm_model_openrouter": "anthropic/claude-sonnet-4.5",
    "llm_model_ollama": "",  # chosen via Settings → Detect; blank = not picked yet
    "llm_model_lmstudio": "",
    "llm_model_custom": "",
    "llm_base_url_custom": "",
    "llm_rates": {},  # {provider_id: [input_$_per_M, output_$_per_M]} user overrides; blank = preset default
}


def get_app_data_dir() -> Path:
    path = Path(os.environ.get("APPDATA", str(Path.home()))) / "CampaignScribe"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    return get_app_data_dir() / "data.db"


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def get_prompts_dir() -> Path:
    path = get_app_data_dir() / "prompts"
    path.mkdir(exist_ok=True)
    return path


def load_config() -> dict[str, Any]:
    p = get_config_path()
    if not p.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        return merged
    except Exception as e:
        log_exception("config.load_config: corrupt config.json, using defaults", e)
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict[str, Any]) -> None:
    p = get_config_path()
    safe = {k: cfg.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG}
    # Atomic write so a crash mid-save can't leave a truncated config.json.
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def get_last_dir(kind: str) -> str:
    """Last-used directory for a file-dialog category ('audio' or 'json').
    Returns '' if unknown, which file dialogs treat as 'use the default'."""
    return load_config().get(f"last_{kind}_dir", "") or ""


def set_last_dir(kind: str, path: str) -> None:
    """Remember the directory of a chosen file (or folder) for next time."""
    if not path:
        return
    d = path if os.path.isdir(path) else os.path.dirname(path)
    key = f"last_{kind}_dir"
    if d and key in DEFAULT_CONFIG:
        cfg = load_config()
        cfg[key] = d
        save_config(cfg)


_LEGACY_ANTHROPIC_USERNAME = "anthropic_api_key"


def _provider_key_username(provider_id: str) -> str:
    return f"llm_key_{provider_id}"


def save_provider_key(provider_id: str, key: str) -> None:
    """Store an LLM provider's API key in Credential Manager (stripped; '' clears)."""
    keyring.set_password(SERVICE_NAME, _provider_key_username(provider_id), (key or "").strip())


def get_provider_key(provider_id: str) -> str:
    """Read an LLM provider's key. For 'anthropic', fall back to the pre-Phase-2
    'anthropic_api_key' entry so existing installs keep working; that legacy
    entry is read-only (never written or deleted here)."""
    val = keyring.get_password(SERVICE_NAME, _provider_key_username(provider_id)) or ""
    if not val and provider_id == "anthropic":
        val = keyring.get_password(SERVICE_NAME, _LEGACY_ANTHROPIC_USERNAME) or ""
    return val


def save_anthropic_key(key: str) -> None:
    save_provider_key("anthropic", key)


def get_anthropic_key() -> str:
    return get_provider_key("anthropic")


def get_error_log_path() -> Path:
    return get_app_data_dir() / "errors.log"


def log_exception(context: str, exc: BaseException) -> str:
    """Append a formatted traceback to errors.log. Returns the log path."""
    import traceback
    from datetime import datetime

    log_path = get_error_log_path()
    text = traceback.format_exception(type(exc), exc, exc.__traceback__)
    block = f"\n===== {datetime.now().isoformat(timespec='seconds')} | {context} =====\n" + "".join(
        text
    )
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception:
        pass
    try:
        from app.core import crash_reporting

        crash_reporting.capture(exc)
    except Exception:
        pass
    return str(log_path)
