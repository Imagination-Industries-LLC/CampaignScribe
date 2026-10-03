"""factory: presets, make_provider/get_provider wiring, readiness checks, unknown-id fallback."""

from __future__ import annotations

import pytest

from app import config
from app.core import llm
from app.core.llm import factory


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
    assert list(llm.PRESETS) == [
        "anthropic",
        "gemini",
        "openrouter",
        "ollama",
        "lmstudio",
        "custom",
    ]
    a = llm.PRESETS["anthropic"]
    assert a.display_name == "Claude"
    assert a.default_model == "claude-sonnet-5-5"
    assert a.needs_key and not a.needs_base_url and not a.supports_json_mode
    c = llm.PRESETS["custom"]
    assert c.needs_base_url and not c.needs_key and not c.supports_json_mode
    assert llm.PRESETS["openrouter"].supports_json_mode
    for p in llm.PRESETS.values():
        assert p.vendor_label
        if p.provider_id != "custom" and not p.local_runtime:
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


def test_make_provider_requires_key_for_key_presets():
    with pytest.raises(llm.LLMError) as ei:
        llm.make_provider("openrouter", model="m", api_key="")
    assert ei.value.kind == "missing_key"
    c = llm.make_provider("custom", model="llama3", api_key="", base_url="http://localhost:1/v1")
    assert c.provider_id == "custom"


def test_config_defaults_match_presets():
    for pid, preset in llm.PRESETS.items():
        assert config.DEFAULT_CONFIG[f"llm_model_{pid}"] == preset.default_model


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
    monkeypatch.setattr(factory, "_warned_unknown", set())
    logged = []
    monkeypatch.setattr(config, "log_exception", lambda ctx, exc: logged.append((ctx, str(exc))))
    cfg = config.load_config()
    cfg["llm_provider"] = "banana"
    config.save_config(cfg)
    config.save_provider_key("anthropic", "k")
    p = llm.get_provider()
    llm.get_provider()
    assert p.provider_id == "anthropic"
    assert len(logged) == 1 and "banana" in logged[0][1]
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


def test_local_presets_shape():
    o = llm.PRESETS["ollama"]
    assert o.display_name == "Ollama (local)" and o.local_runtime == "ollama"
    assert o.default_model == "" and not o.needs_key and not o.needs_base_url
    assert o.supports_json_mode is True and o.timeout_s == 600.0
    assert o.vendor_label == "your own computer (Ollama)" and o.privacy_url == ""
    s = llm.PRESETS["lmstudio"]
    assert s.display_name == "LM Studio (local)" and s.local_runtime == "lmstudio"
    assert s.supports_json_mode is False and s.timeout_s == 600.0
    assert llm.BASE_URLS["ollama"] == "http://localhost:11434/v1"
    assert llm.BASE_URLS["lmstudio"] == "http://localhost:1234/v1"
    for pid in ("anthropic", "gemini", "openrouter", "custom"):
        assert llm.PRESETS[pid].local_runtime == "" and llm.PRESETS[pid].timeout_s == 120.0


def test_make_provider_local_preset_builds_compat_provider_without_key():
    p = llm.make_provider("ollama", model="qwen2.5:14b", api_key="")
    assert p.provider_id == "ollama" and p.base_url == "http://localhost:11434/v1"
    assert p.model == "qwen2.5:14b" and p.supports_json_mode is True
    assert p._client.kwargs["timeout"] == 600.0
    assert p._client.kwargs["api_key"] == "sk-none"
    s = llm.make_provider("lmstudio", model="phi-4", api_key="")
    assert s.base_url == "http://localhost:1234/v1" and s.supports_json_mode is False


def test_make_provider_local_preset_blank_model_is_missing_key():
    with pytest.raises(llm.LLMError) as ei:
        llm.make_provider("ollama", model="  ", api_key="")
    assert ei.value.kind == "missing_key"
    assert str(ei.value) == (
        "Pick an Ollama (local) model in Settings (⚙): start Ollama and press Detect."
    )


@pytest.mark.parametrize(
    "pid, model, size, expected",
    [
        (
            "anthropic",
            "claude-sonnet-5-5",
            "",
            ["API key required", "$$ per token", "Sent to Anthropic (Claude)", "Frontier"],
        ),
        (
            "gemini",
            "gemini-2.5-flash",
            "",
            ["API key required", "¢ per token", "Sent to Google (Gemini)", "Strong"],
        ),
        (
            "openrouter",
            "x",
            "",
            [
                "API key required",
                "Varies by model",
                "Sent to OpenRouter (which forwards it to the model vendor you chose)",
                "Varies by model",
            ],
        ),
        (
            "custom",
            "x",
            "",
            [
                "Key optional",
                "Varies by model",
                "Sent to the custom endpoint you configured",
                "Varies by model",
            ],
        ),
        (
            "ollama",
            "qwen2.5:14b",
            "14.8B",
            ["No key needed", "Free · local compute", "Stays on your device", "Good"],
        ),
        (
            "ollama",
            "llama3.1:8b",
            "8.0B",
            ["No key needed", "Free · local compute", "Stays on your device", "Basic"],
        ),
        (
            "lmstudio",
            "phi-4",
            "",
            ["No key needed", "Free · local compute", "Stays on your device", "Basic"],
        ),
    ],
)
def test_badges_for_table(pid, model, size, expected):
    assert llm.badges_for(llm.PRESETS[pid], model, size) == expected


def test_not_ready_message_local_without_model_then_ready():
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    config.save_config(cfg)
    assert llm.not_ready_message() == (
        "Pick an Ollama (local) model in Settings (⚙): start Ollama and press Detect."
    )
    assert llm.provider_ready() is False
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    assert llm.not_ready_message() == ""
    assert llm.provider_ready() is True
    assert llm.get_provider().model == "qwen2.5:14b"


def test_lmstudio_not_ready_names_lm_studio():
    cfg = config.load_config()
    cfg["llm_provider"] = "lmstudio"
    config.save_config(cfg)
    assert llm.not_ready_message() == (
        "Pick an LM Studio (local) model in Settings (⚙): start LM Studio and press Detect."
    )
