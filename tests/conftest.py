"""Shared fixtures.

Isolation strategy:
- ``isolate_appdata`` (autouse) points %APPDATA% (and HOME) at a tmp dir so
  config.json / data.db / errors.log never touch the real user profile.
- ``mem_keyring`` (autouse) installs an in-memory keyring backend so
  save/get_anthropic_key work deterministically without the OS credential store.
- ``fake_claude`` swaps app.core.claude_api.make_client for a fake whose
  messages.create() returns queued canned text — no network, no real key.
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


# ---- fake Anthropic client ----
class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.calls.append(kwargs)
        if not self._parent.responses:
            raise AssertionError("FakeClient.messages.create called with no queued response")
        return _FakeMessage(self._parent.responses.pop(0))


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = _FakeMessages(self)


@pytest.fixture
def fake_claude(monkeypatch):
    """Returns a factory: call ``fake_claude(["resp1", "resp2"])`` to install a
    FakeClient and get it back for assertions on ``.calls``."""

    def _install(responses):
        client = FakeClient(responses)
        monkeypatch.setattr("app.core.claude_api.make_client", lambda api_key: client)
        return client

    return _install
