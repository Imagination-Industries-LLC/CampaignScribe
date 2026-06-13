"""External-contact constants + URL builders for the Feedback & Support hub.

The single home for "where things go": the feedback address, the repo, and the
GitHub/mailto URL builders. Pure string/urllib — Tk-free. (Funding URLs are
added here in Slice B.)
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from app import config

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


# --- Support / Pay-What-You-Want (Slice B) ---
# Each platform is a URL; empty string = not configured (no button shown / not in FUNDING.yml).
KOFI_URL = "https://ko-fi.com/campaignscribe"
SPONSORS_URL = ""  # set to "https://github.com/sponsors/Imagination-Industries-LLC" once approved
PATREON_URL = ""  # add when a Patreon page exists

NUDGE_AFTER_SUMMARIES = 3


def funding_links() -> list[tuple[str, str]]:
    """The (label, url) pairs for the funding platforms that are configured, in display order."""
    candidates = [
        ("Ko-fi", KOFI_URL),
        ("GitHub Sponsors", SPONSORS_URL),
        ("Patreon", PATREON_URL),
    ]
    return [(label, url) for label, url in candidates if url]


def record_summary_and_check_nudge() -> bool:
    """Increment the completed-summary counter and report whether the one-time support
    nudge should be shown now (>= NUDGE_AFTER_SUMMARIES and not shown before). Sets the
    'shown' flag when it returns True, so the nudge fires at most once. Tk-free."""
    cfg = config.load_config()
    count = int(cfg.get("summaries_completed", 0)) + 1
    cfg["summaries_completed"] = count
    show = count >= NUDGE_AFTER_SUMMARIES and not cfg.get("support_nudge_shown", False)
    if show:
        cfg["support_nudge_shown"] = True
    config.save_config(cfg)
    return show
