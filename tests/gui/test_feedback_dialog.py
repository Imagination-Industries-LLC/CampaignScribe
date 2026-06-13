# tests/gui/test_feedback_dialog.py
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


def test_dialog_opens_with_actions(root, monkeypatch):
    from app.ui import feedback_dialog

    opened = []
    monkeypatch.setattr(feedback_dialog, "open_url", lambda url: opened.append(url))

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        dlg._email_feedback()
        assert opened and opened[-1].startswith("mailto:")
        # Email body carries the compact build-info header, NOT the error-log bundle.
        assert "CampaignScribe" in opened[-1]
        assert "errors.log" not in opened[-1]
        dlg._open_discussions()
        assert opened[-1].endswith("/discussions")
        dlg._report_problem()
        assert "/issues/new?" in opened[-1]
    finally:
        dlg.destroy()


def test_dialog_renders_four_sections(root):
    from tkinter import ttk

    from app.ui import feedback_dialog

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        frames = [w for w in dlg.winfo_children() if isinstance(w, ttk.Frame)]
        assert len(frames) == 4
    finally:
        dlg.destroy()


def test_copy_email_address(root, monkeypatch):
    from app.core import support
    from app.ui import feedback_dialog

    monkeypatch.setattr(feedback_dialog.messagebox, "showinfo", lambda *a, **k: None)
    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        dlg._copy_email_address()
        assert dlg.clipboard_get() == support.FEEDBACK_EMAIL
        assert support.FEEDBACK_EMAIL == "cs@mikesdmtools.com"
    finally:
        dlg.destroy()


def test_report_problem_overflow_uses_clipboard(root, monkeypatch):
    from app.core import diagnostics
    from app.ui import feedback_dialog

    opened = []
    monkeypatch.setattr(feedback_dialog, "open_url", lambda url: opened.append(url))
    # The overflow path shows a (blocking) info box — stub it so the test doesn't hang.
    monkeypatch.setattr(feedback_dialog.messagebox, "showinfo", lambda *a, **k: None)
    # Force an oversized bundle so the URL exceeds MAX_ISSUE_URL.
    monkeypatch.setattr(diagnostics, "build_diagnostics_bundle", lambda **k: "X" * 9000)

    dlg = feedback_dialog.FeedbackSupportDialog(root)
    root.update_idletasks()
    try:
        dlg._report_problem()
        assert "/issues/new?" in opened[-1]
        assert len(opened[-1]) < 9000
        assert "X" * 9000 in dlg.clipboard_get()
    finally:
        dlg.destroy()
