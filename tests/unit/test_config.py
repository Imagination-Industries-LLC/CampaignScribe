"""Tests for app.config: atomic save, key allowlist, corrupt-file fallback, secrets."""

from __future__ import annotations

import json

from app import config


def test_save_config_is_atomic_and_leaves_no_tmp():
    config.save_config({"default_num_speakers": 7})
    p = config.get_config_path()
    assert p.exists()
    assert not p.with_suffix(p.suffix + ".tmp").exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["default_num_speakers"] == 7


def test_save_config_drops_unknown_keys():
    config.save_config({"default_num_speakers": 3, "evil_key": "x"})
    data = json.loads(config.get_config_path().read_text(encoding="utf-8"))
    assert "evil_key" not in data
    assert set(data).issubset(set(config.DEFAULT_CONFIG))


def test_save_config_fills_missing_keys_with_defaults():
    config.save_config({})
    data = json.loads(config.get_config_path().read_text(encoding="utf-8"))
    assert data["default_whisper_model"] == config.DEFAULT_CONFIG["default_whisper_model"]


def test_load_config_returns_defaults_when_missing():
    assert not config.get_config_path().exists()
    cfg = config.load_config()
    assert cfg["default_num_speakers"] == config.DEFAULT_CONFIG["default_num_speakers"]
    assert config.get_config_path().exists()


def test_load_config_recovers_from_corrupt_file():
    config.get_config_path().write_text("{ this is not json", encoding="utf-8")
    cfg = config.load_config()
    assert cfg == dict(config.DEFAULT_CONFIG)


def test_load_config_merges_and_ignores_unknown_keys():
    config.get_config_path().write_text(
        json.dumps({"default_num_speakers": 9, "bogus": 1}), encoding="utf-8"
    )
    cfg = config.load_config()
    assert cfg["default_num_speakers"] == 9
    assert "bogus" not in cfg


def test_set_and_get_last_dir(tmp_path):
    f = tmp_path / "audio" / "sess.wav"
    f.parent.mkdir(parents=True)
    f.write_text("x")
    config.set_last_dir("audio", str(f))
    assert config.get_last_dir("audio") == str(f.parent)


def test_anthropic_key_roundtrip_via_keyring():
    assert config.get_anthropic_key() == ""
    config.save_anthropic_key("sk-test-123")
    assert config.get_anthropic_key() == "sk-test-123"
