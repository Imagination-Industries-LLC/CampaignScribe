# tests/unit/test_support_links.py
from urllib.parse import parse_qs, urlsplit

from app.core import support


def test_discussions_url_points_at_repo():
    assert support.discussions_url() == (
        "https://github.com/Imagination-Industries-LLC/CampaignScribe/discussions"
    )


def test_new_issue_url_encodes_title_and_body():
    url = support.new_issue_url("Crash on save", "line1\nline2 & more")
    assert url.startswith(
        "https://github.com/Imagination-Industries-LLC/CampaignScribe/issues/new?"
    )
    q = parse_qs(urlsplit(url).query)
    assert q["title"] == ["Crash on save"]
    assert q["body"] == ["line1\nline2 & more"]


def test_mailto_url_encodes_subject_and_body():
    url = support.mailto_url("Feedback (v1.0.0)", "header\n\n— your feedback —")
    assert url.startswith("mailto:")
    assert support.FEEDBACK_EMAIL in url
    q = parse_qs(urlsplit(url).query)
    assert q["subject"] == ["Feedback (v1.0.0)"]
    assert "— your feedback —" in q["body"][0]


def test_issue_url_overflow_helper():
    assert support.issue_url_too_long("x" * (support.MAX_ISSUE_URL + 1)) is True
    assert support.issue_url_too_long("x" * 10) is False
