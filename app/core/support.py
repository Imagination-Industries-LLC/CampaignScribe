"""External-contact constants + URL builders for the Feedback & Support hub.

The single home for "where things go": the feedback address, the repo, and the
GitHub/mailto URL builders. Pure string/urllib — Tk-free. (Funding URLs are
added here in Slice B.)
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

FEEDBACK_EMAIL = "cs@mikesdmtools.com"

REPO_SLUG = "Imagination-Industries-LLC/CampaignScribe"

# GitHub rejects very long issue URLs; above this we fall back to the clipboard.
MAX_ISSUE_URL = 7000


def discussions_url() -> str:
    return f"https://github.com/{REPO_SLUG}/discussions"


def new_issue_url(title: str, body: str) -> str:
    return f"https://github.com/{REPO_SLUG}/issues/new?" + urlencode({"title": title, "body": body})


def issue_url_too_long(url: str) -> bool:
    return len(url) > MAX_ISSUE_URL


def mailto_url(subject: str, body: str) -> str:
    return f"mailto:{FEEDBACK_EMAIL}?" + urlencode(
        {"subject": subject, "body": body}, quote_via=quote
    )
