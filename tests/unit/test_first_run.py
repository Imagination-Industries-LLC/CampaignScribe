"""first_run: offer the welcome once, only while no AI provider is ready."""

from __future__ import annotations

from app import config
from app.core import first_run


def test_offer_when_flag_unset_and_provider_not_ready():
    cfg = config.load_config()
    assert cfg["setup_welcome_shown"] is False
    assert first_run.should_offer_setup(cfg) is True


def test_no_offer_once_flag_set():
    cfg = config.load_config()
    cfg[first_run.SETUP_OFFERED_KEY] = True
    assert first_run.should_offer_setup(cfg) is False


def test_no_offer_when_cloud_key_stored():
    config.save_provider_key("anthropic", "sk-test")
    assert first_run.should_offer_setup(config.load_config()) is False


def test_no_offer_when_local_model_picked():
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    assert first_run.should_offer_setup(cfg) is False


def test_mark_setup_offered_persists_and_keeps_other_keys():
    cfg = config.load_config()
    cfg["theme_mode"] = "light"
    config.save_config(cfg)
    first_run.mark_setup_offered()
    after = config.load_config()
    assert after["setup_welcome_shown"] is True
    assert after["theme_mode"] == "light"
