"""Smoke-test fixtures: startup prompts must never open a blocking modal."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _welcome_never_blocks(monkeypatch):
    monkeypatch.setattr("app.ui.welcome_dialog.ask_setup_choice", lambda master: None)
