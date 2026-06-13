# tests/unit/test_diagnostics.py
from app.core import diagnostics


def test_scrub_replaces_user_home_with_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\alice")
    text = r"error at C:\Users\alice\AppData\Roaming\CampaignScribe\errors.log"
    out = diagnostics.scrub(text)
    assert r"C:\Users\alice" not in out
    assert "~" in out


def test_scrub_drops_email_addresses():
    out = diagnostics.scrub("contact bob.smith@example.com for help")
    assert "bob.smith@example.com" not in out
    assert "[email removed]" in out


def test_bundle_has_version_os_gpu(monkeypatch):
    monkeypatch.setattr(diagnostics, "_gpu_state", lambda: "GPU: none (CPU mode)")
    out = diagnostics.build_diagnostics_bundle(include_log_tail=False)
    from app import __version__

    assert f"CampaignScribe {__version__}" in out
    assert "OS:" in out
    assert "Python:" in out
    assert "GPU: none (CPU mode)" in out


def test_bundle_includes_log_tail_when_asked(monkeypatch, tmp_path):
    log = tmp_path / "errors.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: log)
    out = diagnostics.build_diagnostics_bundle(include_log_tail=True)
    assert "line 499" in out  # tail is present
    assert "line 0" not in out  # head is trimmed (only last ~200 lines)


def test_bundle_log_tail_absent_when_no_log(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: tmp_path / "missing.log")
    out = diagnostics.build_diagnostics_bundle(include_log_tail=True)
    assert "errors.log" in out  # a "(no errors.log)" note, not a crash


def test_email_header_is_compact_no_log(monkeypatch, tmp_path):
    log = tmp_path / "errors.log"
    log.write_text("SECRET LINE\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: log)
    header = diagnostics.build_email_header()
    assert "SECRET LINE" not in header  # email header never includes the log
    from app import __version__

    assert __version__ in header


def test_scrub_is_case_insensitive_for_windows_paths():
    out = diagnostics.scrub(r"opened c:\users\alice\AppData\x.log")
    assert "alice" not in out


def test_scrub_handles_username_with_space():
    out = diagnostics.scrub(r"path C:\Users\john doe\AppData\errors.log")
    assert "doe" not in out
    assert "john" not in out


def test_scrub_drops_multiple_emails():
    out = diagnostics.scrub("a@x.com and b@y.org")
    assert "a@x.com" not in out and "b@y.org" not in out


def test_bundle_scrubs_pii_in_log_tail(monkeypatch, tmp_path):
    # The security-critical flow: a home path in errors.log must be scrubbed in the full bundle.
    log = tmp_path / "errors.log"
    log.write_text(
        r"Traceback: C:\Users\alice\AppData\Roaming\CampaignScribe\boom.py", encoding="utf-8"
    )
    monkeypatch.setattr(diagnostics.config, "get_error_log_path", lambda: log)
    out = diagnostics.build_diagnostics_bundle(include_log_tail=True)
    assert "alice" not in out
    assert "~" in out
