"""Preset table + factory: config/keyring -> a ready Provider. Tk-free."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import config
from app.core.llm.base import LLMError, Provider, missing_key_error
from app.core.llm.local_detect import RUNTIME_NAMES, RUNTIMES, quality_label


@dataclass(frozen=True)
class Preset:
    provider_id: str
    display_name: str  # dropdown + error messages
    vendor_label: str  # "Sent to <vendor_label>" in privacy notes
    default_model: str
    needs_key: bool
    needs_base_url: bool
    supports_json_mode: bool
    privacy_url: str
    key_label: str = "API key required"
    cost_label: str = "Varies by model"
    quality_label: str = "Varies by model"  # local presets: derived per model instead
    timeout_s: float = 120.0
    local_runtime: str = ""  # "" for cloud/custom; "ollama" | "lmstudio" for local presets
    input_per_mtok: float = (
        0.0  # default $ per million input tokens for default_model (0 = unknown/free)
    )
    output_per_mtok: float = 0.0
    chars_per_token: float = 4.0  # input-size heuristic for the cost estimate


PRESETS: dict[str, Preset] = {
    "anthropic": Preset(
        "anthropic",
        "Claude",
        "Anthropic (Claude)",
        "claude-sonnet-5-5",
        True,
        False,
        False,
        "https://www.anthropic.com/legal/privacy",
        cost_label="$$ per token",
        quality_label="Frontier",
        input_per_mtok=2.0,
        output_per_mtok=10.0,
        chars_per_token=2.5,  # measured 2.69 on claude-sonnet-5-5; rounded down (upper bound)
    ),
    "gemini": Preset(
        "gemini",
        "Google Gemini",
        "Google (Gemini)",
        "gemini-2.5-flash",
        True,
        False,
        True,
        "https://ai.google.dev/gemini-api/terms",
        cost_label="¢ per token",
        quality_label="Strong",
        input_per_mtok=0.30,
        output_per_mtok=2.50,
    ),
    "openrouter": Preset(
        "openrouter",
        "OpenRouter",
        "OpenRouter (which forwards it to the model vendor you chose)",
        "anthropic/claude-sonnet-4.5",
        True,
        False,
        True,
        "https://openrouter.ai/privacy",
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        chars_per_token=3.0,  # older Sonnet tokenizer, unmeasured; conservative
    ),
    "ollama": Preset(
        "ollama",
        "Ollama (local)",
        "your own computer (Ollama)",
        "",
        False,
        False,
        True,
        "",
        key_label="No key needed",
        cost_label="Free · local compute",
        quality_label="",
        timeout_s=600.0,
        local_runtime="ollama",
    ),
    "lmstudio": Preset(
        "lmstudio",
        "LM Studio (local)",
        "your own computer (LM Studio)",
        "",
        False,
        False,
        False,
        "",
        key_label="No key needed",
        cost_label="Free · local compute",
        quality_label="",
        timeout_s=600.0,
        local_runtime="lmstudio",
    ),
    "custom": Preset(
        "custom",
        "Custom endpoint",
        "the custom endpoint you configured",
        "",
        False,
        True,
        False,
        "",
        key_label="Key optional",
    ),
}

BASE_URLS = {"openrouter": "https://openrouter.ai/api/v1", **RUNTIMES}


def badges_for(preset: Preset, model_id: str = "", parameter_size: str = "") -> list[str]:
    """[Key, Cost, Privacy, Quality] for the Settings badge row."""
    if preset.local_runtime:
        privacy = "Stays on your device"
        quality = quality_label(parameter_size)
    else:
        privacy = f"Sent to {preset.vendor_label}"
        quality = preset.quality_label
    return [preset.key_label, preset.cost_label, privacy, quality]


def _local_pick_message(preset: Preset) -> str:
    return (
        f"Pick an {preset.display_name} model in Settings (⚙): "
        f"start {RUNTIME_NAMES[preset.local_runtime]} and press Detect."
    )


def make_provider(
    provider_id: str,
    *,
    model: str,
    api_key: str,
    base_url: str = "",
    timeout_s: float | None = None,
) -> Provider:
    """Build an adapter from explicit values (Settings → Test connection uses unsaved ones).

    ``timeout_s`` overrides the preset's request timeout (OpenAI-compatible adapters only).
    """
    preset = PRESETS.get(provider_id)
    if preset is None:
        raise ValueError(f"unknown LLM provider: {provider_id!r}")
    if preset.needs_key and not (api_key or "").strip():
        raise missing_key_error(provider_id, preset.display_name)
    model = (model or "").strip() or preset.default_model
    if preset.local_runtime and not model:
        raise LLMError(provider_id, _local_pick_message(preset), kind="missing_key")
    if provider_id == "anthropic":
        from app.core.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key, model)
    if provider_id == "gemini":
        from app.core.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key, model)
    from app.core.llm.openai_compat_provider import OpenAICompatProvider

    return OpenAICompatProvider(
        api_key,
        model,
        BASE_URLS.get(provider_id, base_url),
        provider_id=provider_id,
        display_name=preset.display_name,
        supports_json_mode=preset.supports_json_mode,
        timeout_s=timeout_s if timeout_s is not None else preset.timeout_s,
        local_runtime=preset.local_runtime,
    )


def _cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return cfg if cfg is not None else config.load_config()


_warned_unknown: set[str] = set()


def _resolve_id(cfg: dict[str, Any]) -> str:
    pid = cfg.get("llm_provider", "anthropic")
    if pid not in PRESETS:
        if repr(pid) not in _warned_unknown:
            _warned_unknown.add(repr(pid))
            config.log_exception(
                "llm.factory: unknown llm_provider in config, falling back to anthropic",
                ValueError(repr(pid)),
            )
        return "anthropic"
    return pid


def active_preset(cfg: dict[str, Any] | None = None) -> Preset:
    return PRESETS[_resolve_id(_cfg(cfg))]


def get_provider(cfg: dict[str, Any] | None = None) -> Provider:
    """The configured provider. Raises LLMError(kind='missing_key') when not set up."""
    c = _cfg(cfg)
    pid = _resolve_id(c)
    return make_provider(
        pid,
        model=c.get(f"llm_model_{pid}", ""),
        api_key=config.get_provider_key(pid),
        base_url=c.get("llm_base_url_custom", ""),
    )


def provider_ready(cfg: dict[str, Any] | None = None) -> bool:
    return not_ready_message(cfg) == ""


def not_ready_message(cfg: dict[str, Any] | None = None) -> str:
    """'' when the active provider can run; otherwise the sentence to show the user."""
    c = _cfg(cfg)
    preset = PRESETS[_resolve_id(c)]
    if preset.needs_base_url:
        base_url = (c.get("llm_base_url_custom", "") or "").strip()
        model = (c.get(f"llm_model_{preset.provider_id}", "") or "").strip()
        if not base_url or not model:
            return f"Set the {preset.display_name} base URL and model in Settings (⚙)."
    if preset.local_runtime:
        model = (c.get(f"llm_model_{preset.provider_id}", "") or "").strip()
        if not model:
            return _local_pick_message(preset)
    if preset.needs_key and not config.get_provider_key(preset.provider_id):
        return f"Add your {preset.display_name} API key in Settings (⚙)."
    return ""


__all__ = [
    "BASE_URLS",
    "LLMError",
    "PRESETS",
    "Preset",
    "active_preset",
    "badges_for",
    "get_provider",
    "make_provider",
    "not_ready_message",
    "provider_ready",
]
