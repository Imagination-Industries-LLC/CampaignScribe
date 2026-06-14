# tests/unit/test_crash_reporting.py
import json
import types

from app.core import crash_reporting


def test_before_send_scrubs_paths_and_emails_and_drops_identity():
    event = {
        "server_name": "MIKE-DESKTOP",
        "user": {"id": "mike", "username": "mike"},
        "exception": {
            "values": [
                {
                    "value": r"boom at C:\Users\mike\AppData\x.log contact bob@example.com",
                    "stacktrace": {"frames": [{"abs_path": r"C:\Users\mike\app\y.py"}]},
                }
            ]
        },
    }
    out = crash_reporting.before_send(event, {})
    assert "server_name" not in out
    assert "user" not in out
    dumped = json.dumps(out)
    assert "mike" not in dumped
    assert "bob@example.com" not in dumped
    assert "~" in dumped


def test_init_noop_when_disabled():
    assert crash_reporting.init(False) is False


def test_init_noop_when_dsn_empty(monkeypatch):
    monkeypatch.setattr(crash_reporting, "DSN", "")
    assert crash_reporting.init(True) is False


def test_init_noop_when_sentry_absent(monkeypatch):
    monkeypatch.setattr(crash_reporting, "DSN", "https://k@o1.ingest.sentry.io/1")
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: None)
    assert crash_reporting.init(True) is False


def test_init_calls_sentry_with_scrubber(monkeypatch):
    calls = {}
    fake = types.SimpleNamespace(init=lambda **kw: calls.update(kw))
    monkeypatch.setattr(crash_reporting, "DSN", "https://k@o1.ingest.sentry.io/1")
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: fake)
    crash_reporting._initialized = False
    assert crash_reporting.init(True) is True
    assert calls["dsn"].startswith("https://")
    assert calls["before_send"] is crash_reporting.before_send
    assert calls["include_local_variables"] is False
    assert calls["send_default_pii"] is False
    assert calls["auto_session_tracking"] is False
    crash_reporting._initialized = False


def test_before_send_fails_closed_on_scrub_error(monkeypatch):
    # If scrubbing raises, before_send must return None (drop the event), never the raw event.
    import app.core.diagnostics as diag

    def _boom(_text):
        raise RuntimeError("scrub exploded")

    monkeypatch.setattr(diag, "scrub", _boom)
    out = crash_reporting.before_send({"server_name": "MIKE", "msg": "secret path"}, {})
    assert out is None


def test_capture_noop_when_not_initialized():
    crash_reporting._initialized = False
    crash_reporting.capture(ValueError("x"))


def test_capture_sends_when_initialized(monkeypatch):
    sent = []
    fake = types.SimpleNamespace(capture_exception=lambda e: sent.append(e))
    monkeypatch.setattr(crash_reporting, "_sentry", lambda: fake)
    crash_reporting._initialized = True
    err = ValueError("boom")
    crash_reporting.capture(err)
    assert sent == [err]
    crash_reporting._initialized = False
