"""SettingsDialog AI-model section: provider switch, per-provider persistence, Test connection."""

from __future__ import annotations

import tkinter as tk

import pytest

from app import config
from app.core import llm

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No display: {e}")
    r.withdraw()
    try:
        yield r
    finally:
        r.destroy()


def _open(root):
    from app.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(root)
    root.update_idletasks()
    return dlg


def _select(dlg, display_name):
    dlg.llm_provider_var.set(display_name)
    dlg._on_provider_change()
    dlg.update_idletasks()


def test_opens_on_saved_provider_with_its_values(root):
    cfg = config.load_config()
    cfg["llm_provider"] = "gemini"
    cfg["llm_model_gemini"] = "gemini-2.5-pro"
    config.save_config(cfg)
    config.save_provider_key("gemini", "g-key")
    dlg = _open(root)
    try:
        assert dlg.llm_provider_var.get() == "Google Gemini"
        assert dlg.llm_model_var.get() == "gemini-2.5-pro"
        assert dlg.api_var.get() == "g-key"
        assert dlg.llm_base_url_row.winfo_manager() == ""  # hidden for non-custom
    finally:
        dlg.destroy()


def test_switching_provider_swaps_fields_and_keeps_edits(root):
    config.save_provider_key("anthropic", "a-key")
    dlg = _open(root)
    try:
        assert dlg.api_var.get() == "a-key"
        dlg.llm_model_var.set("claude-opus-5-5")
        _select(dlg, "OpenRouter")
        assert dlg.api_var.get() == ""
        assert dlg.llm_model_var.get() == llm.PRESETS["openrouter"].default_model
        dlg.api_var.set("or-key")
        _select(dlg, "Custom endpoint")
        assert dlg.llm_base_url_row.winfo_manager() == "grid"
        assert dlg.llm_key_row.winfo_manager() == "grid"  # key optional but still editable
        _select(dlg, "Claude")
        assert dlg.llm_model_var.get() == "claude-opus-5-5"
        assert dlg.api_var.get() == "a-key"
        assert dlg._llm_state["openrouter"]["key"] == "or-key"
    finally:
        dlg.destroy()


def test_save_persists_every_touched_provider_and_strips_base_url(root):
    dlg = _open(root)
    dlg.api_var.set(" a-key \n")
    _select(dlg, "Custom endpoint")
    dlg.llm_model_var.set("llama3")
    dlg.llm_base_url_var.set("  http://localhost:11434/v1/ ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    cfg = config.load_config()
    assert cfg["llm_provider"] == "custom"
    assert cfg["llm_model_custom"] == "llama3"
    assert cfg["llm_base_url_custom"] == "http://localhost:11434/v1"
    assert config.get_provider_key("anthropic") == "a-key"
    assert config.get_provider_key("custom") == ""


def test_blank_model_saves_preset_default(root):
    dlg = _open(root)
    dlg.llm_model_var.set("   ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == "claude-sonnet-5-5"


def test_test_connection_reports_success_and_error(root, monkeypatch):
    class _Good:
        display_name = "Claude"
        model = "claude-sonnet-5-5"

        def complete(self, prompt, max_tokens, json_mode=False):
            return "OK"

    monkeypatch.setattr(llm, "make_provider", lambda *a, **k: _Good())
    import app.ui.settings_dialog as sd

    monkeypatch.setattr(sd.llm, "make_provider", lambda *a, **k: _Good())
    dlg = _open(root)
    try:
        dlg.api_var.set("k")
        dlg._test_connection(_sync=True)
        dlg.update_idletasks()
        assert dlg.llm_test_label.cget("text").startswith("✓ Connected")
        assert "claude-sonnet-5-5" in dlg.llm_test_label.cget("text")

        def _bad(*a, **k):
            raise llm.LLMError(
                "anthropic", "Claude rejected the API key. Check Settings (⚙).", kind="auth"
            )

        monkeypatch.setattr(sd.llm, "make_provider", _bad)
        dlg._test_connection(_sync=True)
        dlg.update_idletasks()
        assert "rejected the API key" in dlg.llm_test_label.cget("text")
    finally:
        dlg.destroy()


def test_test_connection_result_after_destroy_is_ignored(root, monkeypatch):
    dlg = _open(root)
    dlg.destroy()
    root.update_idletasks()
    # Simulate the worker's completion callback arriving after the dialog is gone.
    dlg._report_test_result("✓ Connected (x)")  # must not raise TclError
