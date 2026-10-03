"""Shared fixtures.

Isolation strategy:
- ``isolate_appdata`` (autouse) points %APPDATA% (and HOME) at a tmp dir so
  config.json / data.db / errors.log never touch the real user profile.
- ``mem_keyring`` (autouse) installs an in-memory keyring backend so
  save/get_anthropic_key work deterministically without the OS credential store.
- ``fake_provider`` installs a ScriptedProvider (queued canned text) and patches
  app.core.llm.get_provider to return it — no network, no SDK, no real key.
"""

from __future__ import annotations

import keyring
import pytest
from keyring.backend import KeyringBackend


# ---- in-memory keyring backend ----
class _InMemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self):
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def mem_keyring():
    # NOTE: keyring is a process-level global. This fixture is correct for
    # sequential runs but is NOT safe under pytest-xdist worker parallelism.
    # Do not add `-n auto` without replacing this with per-test isolation.
    prev = keyring.get_keyring()
    keyring.set_keyring(_InMemoryKeyring())
    yield
    keyring.set_keyring(prev)


@pytest.fixture(autouse=True)
def isolate_appdata(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return appdata


# ---- scripted LLM provider ----
class ScriptedProvider:
    """Provider double: pops queued responses, records every call."""

    provider_id = "scripted"
    display_name = "Scripted"
    model = "scripted-1"

    def __init__(self, responses, supports_json_mode=True):
        self.responses = list(responses)
        self.supports_json_mode = supports_json_mode
        self.calls: list[dict] = []

    def complete(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens, "json_mode": json_mode})
        if not self.responses:
            raise AssertionError("ScriptedProvider.complete called with no queued response")
        return self.responses.pop(0)


@pytest.fixture
def fake_provider(monkeypatch):
    """Returns a factory: ``p = fake_provider(["resp1", "resp2"])`` installs a
    ScriptedProvider as the app's active provider and returns it for assertions on ``.calls``."""

    def _install(responses, *, supports_json_mode=True):
        p = ScriptedProvider(responses, supports_json_mode=supports_json_mode)
        monkeypatch.setattr("app.core.llm.factory.get_provider", lambda cfg=None: p)
        monkeypatch.setattr("app.core.llm.get_provider", lambda cfg=None: p)
        return p

    return _install
