"""GUI-test fixtures.

CI never fetches the diarization weights (they are a build-time download), so the
Transcribe / Refine / Discover pre-flight would raise MissingModelError and open a
modal error box that blocks the runner. Default every GUI test to "weights present";
tests that exercise the missing case override this with their own monkeypatch.
"""

from __future__ import annotations

import pytest

from app.core import models


@pytest.fixture(autouse=True)
def _diarization_weights_present(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "diarization_dir", lambda: tmp_path / models.DIARIZATION_DIRNAME)


@pytest.fixture(autouse=True)
def _welcome_never_blocks(monkeypatch):
    """AppWindow schedules startup prompts on a timer. On a fresh config the
    welcome would open a modal that waits, which hangs CI if a test pumps events.
    Flow tests override this with their own recorder."""
    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", lambda master: None)


_MODALS = (
    ("tkinter.messagebox", "showinfo"),
    ("tkinter.messagebox", "showwarning"),
    ("tkinter.messagebox", "showerror"),
    ("tkinter.messagebox", "askyesno"),
    ("tkinter.messagebox", "askokcancel"),
    ("tkinter.messagebox", "askyesnocancel"),
    ("tkinter.messagebox", "askretrycancel"),
    ("tkinter.messagebox", "askquestion"),
    ("tkinter.simpledialog", "askstring"),
    ("tkinter.simpledialog", "askinteger"),
    ("tkinter.simpledialog", "askfloat"),
    ("tkinter.filedialog", "askopenfilename"),
    ("tkinter.filedialog", "askopenfilenames"),
    ("tkinter.filedialog", "asksaveasfilename"),
    ("tkinter.filedialog", "askdirectory"),
)


@pytest.fixture(autouse=True)
def _no_unpatched_modal(monkeypatch):
    """A real modal passes on a desktop that auto-dismisses it but hangs CI. Fail instead.
    Tests that expect a dialog patch it on the same module object, overriding this."""
    import importlib

    for mod_name, attr in _MODALS:
        mod = importlib.import_module(mod_name)

        def _fail(*args, _name=f"{mod_name}.{attr}", **kwargs):
            pytest.fail(f"unpatched modal: {_name}{args!r}")

        monkeypatch.setattr(mod, attr, _fail)
