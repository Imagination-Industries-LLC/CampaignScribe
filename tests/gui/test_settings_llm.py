"""SettingsDialog AI-model section: provider switch, per-provider persistence, Test connection."""

from __future__ import annotations

import gc
import threading
import tkinter as tk

import pytest

from app import config
from app.core import llm
from app.core.llm import local_detect

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
        gc.collect()  # free dialog Tk variables on the Tk thread, not a detect worker
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


def test_model_equal_to_default_saves_blank_and_blank_saves_blank(root):
    dlg = _open(root)
    assert dlg.llm_model_var.get() == "claude-sonnet-5-5"  # field shows the default
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == ""  # not pinned
    dlg = _open(root)
    dlg.llm_model_var.set("   ")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == ""


def test_custom_model_id_still_saved(root):
    dlg = _open(root)
    dlg.llm_model_var.set("claude-opus-5-5")
    try:
        dlg._save()
    except tk.TclError:
        pass
    assert config.load_config()["llm_model_anthropic"] == "claude-opus-5-5"


def test_test_connection_reports_success_and_error(root, monkeypatch):
    class _Good:
        display_name = "Claude"
        model = "claude-sonnet-5-5"

        seen_max_tokens = []

        def complete(self, prompt, max_tokens, json_mode=False):
            self.seen_max_tokens.append(max_tokens)
            return "OK"

    good = _Good()
    monkeypatch.setattr(llm, "make_provider", lambda *a, **k: good)
    import app.ui.settings_dialog as sd

    monkeypatch.setattr(sd.llm, "make_provider", lambda *a, **k: good)
    dlg = _open(root)
    try:
        dlg.api_var.set("k")
        dlg._test_connection(_sync=True)
        dlg.update_idletasks()
        assert dlg.llm_test_label.cget("text").startswith("✓ Connected")
        assert "claude-sonnet-5-5" in dlg.llm_test_label.cget("text")
        assert good.seen_max_tokens == [64]

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


def _scripted_detect(monkeypatch, result_by_runtime):
    calls = []

    def _detect(runtime_id, *, base_url=None, timeout_s=1.5):
        calls.append(runtime_id)
        return result_by_runtime[runtime_id]

    import app.ui.settings_dialog as sd

    monkeypatch.setattr(sd.local_detect, "detect", _detect)
    return calls


_OLLAMA_OK = local_detect.DetectResult(
    "ollama",
    True,
    [
        local_detect.LocalModel("qwen2.5:14b", "14.8B"),
        local_detect.LocalModel("llama3.1:8b", "8.0B"),
    ],
)
_OLLAMA_DOWN = local_detect.DetectResult("ollama", False, [], "URLError: [WinError 10061] refused")
_OLLAMA_EMPTY = local_detect.DetectResult("ollama", True, [])


def test_badge_row_for_cloud_and_local(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        assert dlg.llm_badge_label.cget("text") == (
            "API key required · $$ per token · Sent to Anthropic (Claude) · Frontier"
        )
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert dlg.llm_badge_label.cget("text") == (
            "No key needed · Free · local compute · Stays on your device · Good"
        )
        dlg.llm_model_var.set("llama3.1:8b")
        dlg._refresh_badges()
        assert dlg.llm_badge_label.cget("text").endswith("· Basic")
    finally:
        dlg.destroy()


def test_local_preset_hides_key_and_url_rows_and_shows_detect(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        assert dlg.llm_detect_btn.winfo_manager() == ""
        _select(dlg, "Ollama (local)")
        assert dlg.llm_key_row.winfo_manager() == ""
        assert dlg.llm_base_url_row.winfo_manager() == ""
        assert dlg.llm_detect_btn.winfo_manager() == "pack"
        _select(dlg, "Claude")
        assert dlg.llm_key_row.winfo_manager() == "grid"
        assert dlg.llm_detect_btn.winfo_manager() == ""
    finally:
        dlg.destroy()


def test_detect_fills_combobox_and_selects_first_when_blank(root, monkeypatch):
    calls = _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert calls and all(c == "ollama" for c in calls)  # auto-run on select + explicit run
        assert list(dlg.llm_model_combo.cget("values")) == ["qwen2.5:14b", "llama3.1:8b"]
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
        assert "2 models found" in dlg.llm_local_label.cget("text")
        assert "speaker-ID JSON" in dlg.llm_local_label.cget("text")
        try:
            dlg._save()
        except tk.TclError:
            pass
        cfg = config.load_config()
        assert cfg["llm_provider"] == "ollama" and cfg["llm_model_ollama"] == "qwen2.5:14b"
    finally:
        try:
            dlg.destroy()
        except tk.TclError:
            pass


def test_detect_runtime_down_shows_start_hint(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_DOWN})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        text = dlg.llm_local_label.cget("text")
        assert text.startswith("Ollama (local) not running — start it, then press Detect.")
        assert "10061" in text
        assert dlg.llm_model_var.get() == ""
        assert str(dlg.llm_detect_btn.cget("state")) == "normal"
    finally:
        dlg.destroy()


def test_detect_with_no_models_explains_pull(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_EMPTY})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        dlg._run_detect(_sync=True)
        assert dlg.llm_local_label.cget("text") == (
            "0 models found — run `ollama pull <model>` (e.g. qwen2.5:14b), then press Detect."
        )
        assert list(dlg.llm_model_combo.cget("values")) == []
    finally:
        dlg.destroy()


def test_detect_result_for_other_provider_does_not_touch_current_fields(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_DOWN})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")
        _select(dlg, "Claude")  # user moved on before a (late) Ollama result arrives
        dlg.llm_model_var.set("claude-opus-5-5")
        dlg._apply_detect_result(_OLLAMA_OK)
        assert dlg.llm_model_var.get() == "claude-opus-5-5"
        assert dlg._llm_state["ollama"]["detected"] == _OLLAMA_OK.models
        assert dlg._llm_state["ollama"]["model"] == "qwen2.5:14b"
        _select(dlg, "Ollama (local)")
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
        assert list(dlg.llm_model_combo.cget("values")) == ["qwen2.5:14b", "llama3.1:8b"]
    finally:
        dlg.destroy()


def test_detect_threaded_path_applies_via_queue(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    try:
        _select(dlg, "Ollama (local)")  # auto-runs the threaded detect
        for _ in range(100):
            dlg.update()
            if dlg.llm_model_var.get():
                break
            threading.Event().wait(0.02)
        assert dlg.llm_model_var.get() == "qwen2.5:14b"
    finally:
        dlg.destroy()


def test_detect_poll_after_destroy_is_quiet(root, monkeypatch):
    _scripted_detect(monkeypatch, {"ollama": _OLLAMA_OK})
    dlg = _open(root)
    _select(dlg, "Ollama (local)")
    dlg.destroy()
    root.update()
    dlg._poll_detect()  # must not raise
    dlg._apply_detect_result(_OLLAMA_OK)  # must not raise
