"""Summarize tab: live cost estimate line and the confirm-cost gate at Start."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from app import config
from app.core import library, speakers_io
from app.data import db

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


def _tab(root):
    db.init_db()
    from app.ui.summarize_tab import SummarizeTab

    tab = SummarizeTab(root, types.SimpleNamespace(notebook=None))
    root.update_idletasks()
    return tab


def _transcript(tmp_path, name="t1.txt", chars=150_000):
    p = tmp_path / name
    p.write_text("x" * chars, encoding="utf-8")
    return str(p)


def _add(tab, path):
    tab.transcript_files.append(path)
    tab.files_box.insert("end", path)
    tab._refresh_estimate()


def test_label_empty_state_and_known_estimate(root, tmp_path):
    tab = _tab(root)
    assert tab.estimate_var.get() == "Add transcript files to see an estimate."
    _add(tab, _transcript(tmp_path))
    text = tab.estimate_var.get()
    assert text.startswith("Estimate: ~")  # ~38k-40k depending on the default prompt length
    assert "input tokens · up to ~4k output · est. up to ~$" in text
    assert "(Claude @ $2/$10 per M)" in text and "consolidate" in text


def test_label_updates_on_clear_and_settings_change(root, tmp_path):
    tab = _tab(root)
    _add(tab, _transcript(tmp_path))
    tab._clear_files()
    assert tab.estimate_var.get() == "Add transcript files to see an estimate."
    _add(tab, _transcript(tmp_path))
    cfg = config.load_config()
    cfg["llm_provider"] = "ollama"
    cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    tab.on_settings_changed()
    assert tab.estimate_var.get().endswith("· Free · local compute (Ollama (local))")
    cfg["llm_provider"] = "anthropic"
    cfg["llm_rates"] = {"anthropic": [4.0, 20.0]}
    config.save_config(cfg)
    tab.on_settings_changed()
    assert "(Claude @ $4/$20 per M)" in tab.estimate_var.get()


def test_estimate_skips_missing_files(root, tmp_path):
    tab = _tab(root)
    gone = str(tmp_path / "gone.txt")
    tab.transcript_files.append(gone)
    tab.files_box.insert("end", gone)
    tab._refresh_estimate()  # must not raise
    text = tab.estimate_var.get()
    assert text.startswith("Estimate: ~") and "input tokens · up to ~4k output" in text


def _arm_start(tab, tmp_path, monkeypatch, provider="anthropic"):
    slug = library.create_campaign("Strahd")
    library.add_version(slug, speakers_io.profiles_to_speakers_doc("Strahd", "", []))
    tab.speakers_path = str(library.current_version_path(slug))
    _add(tab, _transcript(tmp_path))
    tab.out_var.set(str(tmp_path / "out"))
    cfg = config.load_config()
    cfg["llm_provider"] = provider
    if provider == "ollama":
        cfg["llm_model_ollama"] = "qwen2.5:14b"
    config.save_config(cfg)
    if provider == "anthropic":
        config.save_provider_key("anthropic", "k")
    started = []

    class _Thread:
        def __init__(self, *a, **k):
            started.append(k.get("target"))

        def start(self):
            pass

    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.threading, "Thread", _Thread)
    return started


def test_start_confirm_no_aborts_yes_proceeds(root, tmp_path, monkeypatch):
    tab = _tab(root)
    started = _arm_start(tab, tmp_path, monkeypatch)
    asked = []
    import app.ui.summarize_tab as st

    monkeypatch.setattr(
        st.messagebox, "askyesno", lambda title, msg, **k: (asked.append((title, msg)), False)[1]
    )
    tab._start()
    assert asked and asked[0][0] == "Confirm cost" and "Continue?" in asked[0][1]
    assert started == [] and not tab._busy
    assert not (tmp_path / "out").exists()
    monkeypatch.setattr(st.messagebox, "askyesno", lambda title, msg, **k: True)
    tab._start()
    assert len(started) == 1


def test_start_on_local_never_prompts(root, tmp_path, monkeypatch):
    tab = _tab(root)
    started = _arm_start(tab, tmp_path, monkeypatch, provider="ollama")
    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.messagebox, "askyesno", lambda *a, **k: pytest.fail("must not prompt"))
    tab._start()
    assert len(started) == 1


def test_two_files_carry_their_own_prompt_and_context(root, tmp_path):
    tab = _tab(root)
    p = _transcript(tmp_path)
    _add(tab, p)
    a = tab._current_estimate()[0].input_tokens
    _add(tab, _transcript(tmp_path, "t2.txt"))
    b = tab._current_estimate()[0].input_tokens
    assert abs(b - 2 * a) <= 1


def test_file_hooks_refresh_estimate_without_manual_call(root, tmp_path, monkeypatch):
    import app.ui.summarize_tab as st

    tab = _tab(root)
    empty = "Add transcript files to see an estimate."
    assert tab.estimate_var.get() == empty
    path = _transcript(tmp_path)
    monkeypatch.setattr(st.filedialog, "askopenfilenames", lambda **k: (path,))
    tab._add_files()
    assert tab.estimate_var.get() != empty
    tab.files_box.selection_set(0)
    tab._remove_files()
    assert tab.estimate_var.get() == empty


def test_start_on_unknown_rates_never_prompts(root, tmp_path, monkeypatch):
    tab = _tab(root)
    started = _arm_start(tab, tmp_path, monkeypatch, provider="custom")
    cfg = config.load_config()
    cfg["llm_base_url_custom"] = "http://localhost:1/v1"
    cfg["llm_model_custom"] = "m"
    config.save_config(cfg)
    import app.ui.summarize_tab as st

    monkeypatch.setattr(st.messagebox, "askyesno", lambda *a, **k: pytest.fail("must not prompt"))
    tab._refresh_estimate()
    tab._start()
    assert len(started) == 1
    assert "cost unknown" in tab.estimate_var.get()
