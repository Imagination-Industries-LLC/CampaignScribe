# tests/unit/test_support_nudge.py
from app.core import support


def test_funding_links_includes_only_configured(monkeypatch):
    monkeypatch.setattr(support, "KOFI_URL", "https://ko-fi.com/campaignscribe")
    monkeypatch.setattr(support, "SPONSORS_URL", "")
    monkeypatch.setattr(support, "PATREON_URL", "")
    links = support.funding_links()
    assert links == [("Ko-fi", "https://ko-fi.com/campaignscribe")]


def test_funding_links_adds_sponsors_when_set(monkeypatch):
    monkeypatch.setattr(support, "KOFI_URL", "https://ko-fi.com/campaignscribe")
    monkeypatch.setattr(
        support, "SPONSORS_URL", "https://github.com/sponsors/Imagination-Industries-LLC"
    )
    monkeypatch.setattr(support, "PATREON_URL", "")
    labels = [label for label, _ in support.funding_links()]
    assert labels == ["Ko-fi", "GitHub Sponsors"]


def test_nudge_fires_once_on_third_summary(monkeypatch):
    store = {"summaries_completed": 0, "support_nudge_shown": False}
    monkeypatch.setattr(support.config, "load_config", lambda: dict(store))
    monkeypatch.setattr(support.config, "save_config", lambda cfg: store.update(cfg))

    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 1
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 2
    assert support.record_summary_and_check_nudge() is True
    assert store["summaries_completed"] == 3
    assert store["support_nudge_shown"] is True
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 4


def test_nudge_does_not_fire_if_already_shown(monkeypatch):
    store = {"summaries_completed": 10, "support_nudge_shown": True}
    monkeypatch.setattr(support.config, "load_config", lambda: dict(store))
    monkeypatch.setattr(support.config, "save_config", lambda cfg: store.update(cfg))
    assert support.record_summary_and_check_nudge() is False
    assert store["summaries_completed"] == 11
