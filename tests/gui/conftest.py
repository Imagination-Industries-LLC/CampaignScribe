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
