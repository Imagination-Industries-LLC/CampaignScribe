"""App-wide configuration: paths, settings, and keyring-backed secrets."""

from __future__ import annotations

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
    "last_output_folder": "",
    "last_audio_dir": "",
    "last_json_dir": "",
    "window_width": 1000,
    "window_height": 760,
    "window_x": -1,
    "window_y": -1,
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
        return dict(DEFAULT_CONFIG)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        return merged
    except Exception as e:
        log_exception("config.load_config: corrupt config.json, using defaults", e)
        return dict(DEFAULT_CONFIG)


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


def save_anthropic_key(key: str) -> None:
    keyring.set_password(SERVICE_NAME, "anthropic_api_key", key or "")


def get_anthropic_key() -> str:
    return keyring.get_password(SERVICE_NAME, "anthropic_api_key") or ""


def save_huggingface_token(token: str) -> None:
    keyring.set_password(SERVICE_NAME, "huggingface_token", token or "")


def get_huggingface_token() -> str:
    return keyring.get_password(SERVICE_NAME, "huggingface_token") or ""


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
    return str(log_path)
