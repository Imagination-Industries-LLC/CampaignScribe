"""Discover worker finishing after the Edit Profile window was closed must not raise
(errors.log 2026-06-15: TclError 'bad window path name ...!scrollableframe.!canvas.!frame'
from EditProfileWindow.apply -> SpeakerEditor.__init__)."""

from __future__ import annotations

import threading
import tkinter as tk
import types

import pytest

from app.core import library, speakers_io
from app.data import db

pytestmark = [
    pytest.mark.gui,
    # A worker-thread exception (e.g. after() on a dead widget) must fail the test, not warn.
    pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning"),
]


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


def _app():
    return types.SimpleNamespace(notebook=None, open_home=lambda: None)


def _seeded_campaign():
    slug = library.create_campaign("Strahd")
    doc = speakers_io.profiles_to_speakers_doc("Strahd", "", [])
    library.add_version(slug, doc)
    return slug


def test_discover_result_after_window_closed_is_dropped_without_error(root, monkeypatch, tmp_path):
    db.init_db()
    slug = _seeded_campaign()

    # Capture Tk callback exceptions instead of letting Tk print them.
    callback_errors: list[BaseException] = []
    root.report_callback_exception = lambda exc, val, tb: callback_errors.append(val)

    release = threading.Event()
    started = threading.Event()
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF")

    class _FakePipeline:
        def __init__(self, **kwargs):
            pass

        def transcribe_file(self, path, **kwargs):
            started.set()
            release.wait(timeout=10)  # block until the test has closed the window
            return [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "hi"}]

        def close(self):
            pass

    monkeypatch.setattr("app.core.audio.convert_to_wav", lambda p, max_seconds=None: str(wav))
    monkeypatch.setattr("app.core.transcriber.TranscriptionPipeline", _FakePipeline)
    monkeypatch.setattr(
        "app.core.speaker_id.discover_speakers",
        lambda segments, provider: {
            "profiles": [{"source_speaker_id": "SPEAKER_00", "suggested_display_name": "Mike"}]
        },
    )
    monkeypatch.setattr("app.core.llm.get_provider", lambda cfg=None: object())
    monkeypatch.setattr("app.core.llm.provider_ready", lambda cfg=None: True)

    from app.ui.edit_profile_window import EditProfileWindow

    win = EditProfileWindow(root, _app(), slug)
    root.update_idletasks()
    win.start_discover(str(wav))
    assert started.wait(timeout=5), "discover worker never started"

    # User closes the window (◂ Home) while discovery is still running.
    win._back_home()
    root.update()
    assert not win.winfo_exists()

    # Discovery completes after the window is gone. The worker schedules apply() via
    # after(), which only works while the main thread is inside mainloop (as in the app).
    release.set()
    root.after(1500, root.quit)
    root.mainloop()

    assert callback_errors == [], f"Tk callback raised: {callback_errors!r}"
