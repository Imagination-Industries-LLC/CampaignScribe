from app import config


def test_log_exception_routes_to_crash_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_error_log_path", lambda: tmp_path / "errors.log")
    captured = []
    from app.core import crash_reporting

    monkeypatch.setattr(crash_reporting, "capture", lambda exc: captured.append(exc))
    err = ValueError("boom")
    config.log_exception("ctx", err)
    assert captured == [err]
