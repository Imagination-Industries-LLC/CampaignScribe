import tkinter as tk

import pytest

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


def test_maybe_show_support_nudge_respects_logic(root, monkeypatch):
    from app.ui import feedback_dialog

    shown = []
    monkeypatch.setattr(feedback_dialog, "show_support_nudge", lambda m: shown.append(m))
    monkeypatch.setattr(feedback_dialog.support, "record_summary_and_check_nudge", lambda: True)
    assert feedback_dialog.maybe_show_support_nudge(root) is True
    assert len(shown) == 1

    monkeypatch.setattr(feedback_dialog.support, "record_summary_and_check_nudge", lambda: False)
    assert feedback_dialog.maybe_show_support_nudge(root) is False
    assert len(shown) == 1


def test_show_support_nudge_builds_dialog(root):
    from app.ui import feedback_dialog

    feedback_dialog.show_support_nudge(root)
    root.update_idletasks()
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops
    for w in tops:
        w.destroy()
