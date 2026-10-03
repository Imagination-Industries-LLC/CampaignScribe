"""factory: presets, make_provider/get_provider wiring, readiness checks, unknown-id fallback."""

from __future__ import annotations

import pytest

from app import config
from app.core import llm


@pytest.fixture(autouse=True)
def _stub_sdks(monkeypatch):
    """Keep the SDK constructors from doing anything (the adapters import lazily)."""
    import anthropic
    import openai
    from google import genai

    class _Dummy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(anthropic, "Anthropic", _Dummy)
    monkeypatch.setattr(genai, "Client", _Dummy)
    monkeypatch.setattr(openai, "OpenAI", _Dummy)


def test_presets_order_and_shape():
    assert list(llm.PRESETS) == ["anthropic", "gemini", "openrouter", "custom"]
    a = llm.PRESETS["anthropic"]
    assert a.display_name == "Claude"
    assert a.default_model == "claude-sonnet-5-5"
    assert a.needs_key and not a.needs_base_url and not a.supports_json_mode
    c = llm.PRESETS["custom"]
    assert c.needs_base_url and not c.needs_key and not c.supports_json_mode
    assert llm.PRESETS["openrouter"].supports_json_mode
    for p in llm.PRESETS.values():
        assert p.vendor_label
        if p.provider_id != "custom":
            assert p.privacy_url.startswith("https://")


def test_make_provider_each_preset():
    p = llm.make_provider("anthropic", model="claude-sonnet-5-5", api_key="k")
    assert p.provider_id == "anthropic" and p.model == "claude-sonnet-5-5"
    g = llm.make_provider("gemini", model="gemini-2.5-flash", api_key="k")
    assert g.provider_id == "gemini"
    o = llm.make_provider("openrouter", model="m", api_key="k")
    assert o.provider_id == "openrouter" and o.base_url == llm.BASE_URLS["openrouter"]
    assert o.display_name == "OpenRouter" and o.supports_json_mode
    c = llm.make_provider(
        "custom", model="llama3", api_key="", base_url="http://localhost:11434/v1/"
    )
    assert c.provider_id == "custom" and c.base_url == "http://localhost:11434/v1"
    assert not c.supports_json_mode


def test_make_provider_unknown_id_raises():
    with pytest.raises(ValueError):
        llm.make_provider("banana", model="x", api_key="k")


def test_get_provider_reads_config_and_keyring():
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    cfg["llm_model_gemini"] = "gemini-2.5-pro"
    config.save_config(cfg)
    config.save_provider_key("gemini", "g-key")
    p = llm.get_provider()
    assert p.provider_id == "gemini"
    assert p.model == "gemini-2.5-pro"


def test_get_provider_blank_model_uses_preset_default():
    cfg = config.load_config()
    cfg["llm_model_anthropic"] = "   "
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    assert llm.get_provider().model == "claude-sonnet-5-5"


def test_get_provider_unknown_id_falls_back_to_anthropic(monkeypatch):
    logged = []
    monkeypatch.setattr(config, "log_exception", lambda ctx, exc: logged.append((ctx, str(exc))))
    cfg = config.load_config()
    cfg["llm_provider"] = "banana"
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    p = llm.get_provider()
    assert p.provider_id == "anthropic"
    assert logged and "banana" in logged[0][1]
    assert llm.active_preset().provider_id == "anthropic"


def test_get_provider_missing_key_raises_llmerror():
    with pytest.raises(llm.LLMError) as ei:
        llm.get_provider()
    assert ei.value.kind == "missing_key"


@pytest.mark.parametrize(
    "provider, key, base_url, model, ready",
    [
        ("anthropic", "", "", "", False),
        ("anthropic", "k", "", "", True),
        ("gemini", "", "", "", False),
        ("gemini", "k", "", "", True),
        ("openrouter", "k", "", "", True),
        ("custom", "", "", "llama3", False),
        ("custom", "", "http://localhost:11434/v1", "", False),
        ("custom", "", "http://localhost:11434/v1", "llama3", True),
    ],
)
def test_provider_ready_truth_table(provider, key, base_url, model, ready):
    cfg = config.load_config()
    cfg["llm_provider"] = provider
    cfg["llm_base_url_custom"] = base_url
    cfg["llm_model_custom"] = model
    config.save_config(cfg)
    if key:
        config.save_provider_key(provider, key)
    assert llm.provider_ready() is ready


def test_not_ready_message_names_provider_or_base_url():
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    config.save_config(cfg)
    assert llm.not_ready_message() == "Add your Google Gemini API key in Settings (⚙)."
    cfg["llm_provider"] = "custom"
    config.save_config(cfg)
    assert llm.not_ready_message() == "Set the Custom endpoint base URL and model in Settings (⚙)."
    config.save_provider_key("anthropic", "k")
    cfg["llm_provider"] = "anthropic"
    config.save_config(cfg)
    assert llm.not_ready_message() == ""
