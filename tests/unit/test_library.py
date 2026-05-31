"""Tests for app.core.library: campaigns, versions, manifest, import/export."""

from __future__ import annotations

import json

from app.core import library

DOC1 = {
    "campaign": "Curse of Strahd",
    "context": "gothic",
    "players": [{"player_name": "Mike"}],
    "known_non_players": [],
    "fallback_policy": {},
}
DOC2 = {
    "campaign": "Curse of Strahd",
    "context": "gothic",
    "players": [{"player_name": "Mike"}, {"player_name": "Jo"}],
    "known_non_players": [],
    "fallback_policy": {},
}


def test_create_and_list_campaign():
    slug = library.create_campaign("Curse of Strahd")
    assert slug == "curse-of-strahd"
    rows = library.list_campaigns()
    assert any(r["slug"] == slug and r["display_name"] == "Curse of Strahd" for r in rows)


def test_slugify_disambiguates_collisions():
    a = library.create_campaign("My Game!")
    b = library.create_campaign("my game")  # slugs to the same base
    assert a != b
    assert a == "my-game"
    assert b.startswith("my-game-")


def test_add_version_advances_current_and_grows_history():
    slug = library.create_campaign("Curse of Strahd")
    v1 = library.add_version(slug, DOC1)
    assert len(library.list_versions(slug)) == 1
    assert library.get_current_doc(slug)["players"] == DOC1["players"]
    v2 = library.add_version(slug, DOC2, label="s4")
    assert v2 != v1
    versions = library.list_versions(slug)
    assert len(versions) == 2
    assert library.get_current_doc(slug)["players"] == DOC2["players"]  # latest is current
    assert any(v["label"] == "s4" for v in versions)


def test_set_current_to_older_version():
    slug = library.create_campaign("C")
    v1 = library.add_version(slug, DOC1)
    library.add_version(slug, DOC2)
    library.set_current(slug, v1)
    assert library.get_current_doc(slug)["players"] == DOC1["players"]


def test_current_version_path_points_at_real_file():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    p = library.current_version_path(slug)
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_import_file_derives_campaign(tmp_path):
    f = tmp_path / "loose.json"
    f.write_text(json.dumps({"campaign": "Wildemount", "players": []}), encoding="utf-8")
    slug = library.import_file(str(f))
    assert slug == "wildemount"
    assert library.get_current_doc(slug)["campaign"] == "Wildemount"


def test_import_file_without_campaign_uses_filename(tmp_path):
    f = tmp_path / "MyParty.json"
    f.write_text(json.dumps({"players": []}), encoding="utf-8")
    slug = library.import_file(str(f))
    assert slug == "myparty"


def test_export_version_copies_bytes(tmp_path):
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    dest = tmp_path / "out" / "exported.json"
    library.export_version(slug, library.list_versions(slug)[0]["file"], str(dest))
    assert dest.exists()
    assert json.loads(dest.read_text(encoding="utf-8"))["campaign"] == "Curse of Strahd"


def test_rename_campaign():
    slug = library.create_campaign("Old Name")
    library.add_version(slug, DOC1)
    new_slug = library.rename_campaign(slug, "New Name")
    assert new_slug == "new-name"
    assert library.get_current_doc(new_slug)["campaign"] == "Curse of Strahd"
    assert all(r["slug"] != slug for r in library.list_campaigns())


def test_delete_campaign():
    slug = library.create_campaign("Doomed")
    library.add_version(slug, DOC1)
    library.delete_campaign(slug)
    assert all(r["slug"] != slug for r in library.list_campaigns())


def test_manifest_recovery_when_corrupt():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    (library._campaign_dir(slug) / "manifest.json").write_text("{ not json", encoding="utf-8")
    rows = library.list_campaigns()  # must not raise
    row = next(r for r in rows if r["slug"] == slug)
    assert row["version_count"] >= 1  # rebuilt from version files on disk


def test_add_version_atomic_no_temp_left():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    leftovers = list(library._campaign_dir(slug).glob("*.tmp"))
    assert leftovers == []


def test_rename_to_same_name_keeps_slug():
    slug = library.create_campaign("Alpha")
    library.add_version(slug, DOC1)
    assert library.rename_campaign(slug, "Alpha") == slug
    assert library.get_current_doc(slug)["campaign"] == "Curse of Strahd"


def test_rebuild_manifest_created_at_is_iso():
    slug = library.create_campaign("C")
    library.add_version(slug, DOC1)
    (library._campaign_dir(slug) / "manifest.json").unlink()
    versions = library.list_versions(slug)  # triggers rebuild
    assert versions[0]["created_at"].count(":") == 2  # ISO time has 2 colons
    assert "T" in versions[0]["created_at"]
