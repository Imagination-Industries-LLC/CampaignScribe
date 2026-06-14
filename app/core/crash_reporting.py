"""Opt-in (default-off), PII-scrubbed crash reporting via Sentry.

Nothing is sent unless the user enables it in Settings AND a DSN is embedded.
The before_send scrubber deep-scrubs every string in the event (home paths -> ~,
emails removed, via diagnostics.scrub) and drops hostname/user identity. sentry-sdk
is imported lazily, so the app runs normally when it is absent. Tk-free.
"""

from __future__ import annotations

# CONTROLLER: embed the Sentry write-only DSN before release. Empty => never reports.
DSN = ""

# Keys whose values can carry identity; dropped wherever they appear in the event.
_DROP_KEYS = {"server_name", "user"}

_initialized = False


def _sentry():
    """Return the sentry_sdk module, or None if it isn't installed."""
    try:
        import sentry_sdk

        return sentry_sdk
    except Exception:
        return None


def _scrub_value(value, scrub):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v, scrub) for k, v in value.items() if k not in _DROP_KEYS}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v, scrub) for v in value]
    return value


def before_send(event, hint=None):
    """Sentry before_send hook: deep-scrub strings + drop identity keys. Returns the
    scrubbed event, or None if scrubbing fails (drop rather than risk leaking PII)."""
    try:
        from app.core.diagnostics import scrub

        return _scrub_value(event, scrub)
    except Exception:
        return None


def init(enabled: bool) -> bool:
    """Initialize Sentry if enabled, a DSN is embedded, and sentry-sdk is present.
    Returns whether reporting is now active. No-op (False) otherwise."""
    global _initialized
    if not enabled or not DSN:
        return False
    sdk = _sentry()
    if sdk is None:
        return False
    sdk.init(
        dsn=DSN,
        before_send=before_send,
        include_local_variables=False,
        send_default_pii=False,
        traces_sample_rate=0.0,
        auto_session_tracking=False,
    )
    _initialized = True
    return True


def init_from_config() -> bool:
    """Init from the persisted opt-in flag (called at startup)."""
    from app import config

    return init(bool(config.load_config().get("crash_reporting_enabled", False)))


def set_enabled(enabled: bool) -> None:
    """Apply a live toggle from Settings: start reporting, or stop all transmission."""
    if enabled:
        init(True)
    else:
        shutdown()


def shutdown() -> None:
    """Stop all transmission immediately (revoke consent)."""
    global _initialized
    if not _initialized:
        return
    sdk = _sentry()
    if sdk is not None:
        try:
            sdk.flush(timeout=2.0)
            client = sdk.get_client()
            if client is not None:
                client.close()
        except Exception:
            pass
    _initialized = False


def capture(exc: BaseException) -> None:
    """Send a (scrubbed, via before_send) exception if reporting is active. Best-effort."""
    if not _initialized:
        return
    sdk = _sentry()
    if sdk is not None:
        try:
            sdk.capture_exception(exc)
        except Exception:
            pass
