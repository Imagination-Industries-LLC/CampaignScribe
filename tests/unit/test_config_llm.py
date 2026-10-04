"""config: llm_* defaults merge into old configs; per-provider keyring + legacy fallback."""

from __future__ import annotations

import json

import keyring

from app import config


def test_new_llm_defaults_merge_into_old_config_json():
    p = config.get_config_path()
    p.write_text(json.dumps({"theme_mode": "light"}), encoding="utf-8")
    cfg = config.load_config()
    assert cfg["theme_mode"] == "light"
    assert cfg["llm_provider"] == "anthropic"
    assert cfg["llm_model_anthropic"] == "claude-sonnet-5-5"
    assert cfg["llm_model_gemini"] == "gemini-2.5-flash"
    assert cfg["llm_model_openrouter"] == "anthropic/claude-sonnet-4.5"
    assert cfg["llm_model_custom"] == ""
    assert cfg["llm_base_url_custom"] == ""
    assert cfg["llm_model_ollama"] == ""
    assert cfg["llm_model_lmstudio"] == ""
    assert cfg["llm_rates"] == {}


def test_provider_key_roundtrip_per_provider():
    config.save_provider_key("gemini", "g-1")
    config.save_provider_key("openrouter", "or-1")
    assert config.get_provider_key("gemini") == "g-1"
    assert config.get_provider_key("openrouter") == "or-1"
    assert config.get_provider_key("custom") == ""
    assert keyring.get_password(config.SERVICE_NAME, "llm_key_gemini") == "g-1"


def test_save_provider_key_strips_whitespace():
    config.save_provider_key("gemini", "  g-2\n")
    assert config.get_provider_key("gemini") == "g-2"


def test_anthropic_legacy_entry_is_read_as_fallback_but_never_written():
    keyring.set_password(config.SERVICE_NAME, "anthropic_api_key", "legacy-key")
    assert config.get_provider_key("anthropic") == "legacy-key"
    assert config.get_anthropic_key() == "legacy-key"

    config.save_anthropic_key("new-key")
    assert config.get_provider_key("anthropic") == "new-key"
    assert keyring.get_password(config.SERVICE_NAME, "llm_key_anthropic") == "new-key"
    assert keyring.get_password(config.SERVICE_NAME, "anthropic_api_key") == "legacy-key"


def test_explicitly_blank_new_key_falls_back_to_legacy():
    keyring.set_password(config.SERVICE_NAME, "anthropic_api_key", "legacy-key")
    config.save_provider_key("anthropic", "")
    assert config.get_provider_key("anthropic") == "legacy-key"


def test_llm_rates_round_trip():
    cfg = config.load_config()
    cfg["llm_rates"] = {"anthropic": [3.0, 15.0]}
    config.save_config(cfg)
    assert config.load_config()["llm_rates"] == {"anthropic": [3.0, 15.0]}
