"""fetch_diarization_weights: hashing, verification, and main() exit codes (no network)."""

from __future__ import annotations

import hashlib

import pytest

from scripts import fetch_diarization_weights as fw


def _write_valid(dest, monkeypatch):
    """Write fake files and point FILES at their real hashes."""
    files = {}
    for rel in fw.FILES:
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        data = f"fake {rel}".encode()
        p.write_bytes(data)
        files[rel] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(fw, "FILES", files)
    return files


def test_pins():
    assert fw.REPO_ID == "pyannote/speaker-diarization-community-1"
    assert fw.REVISION == "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
    assert set(fw.FILES) == {
        "config.yaml",
        "segmentation/pytorch_model.bin",
        "embedding/pytorch_model.bin",
        "plda/plda.npz",
        "plda/xvec_transform.npz",
    }
    assert fw.FILES["embedding/pytorch_model.bin"] == (
        "6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929"
    )
    assert fw.DEFAULT_DEST.name == "speaker-diarization-community-1"
    assert fw.DEFAULT_DEST.parent.name == "models"


def test_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert fw.sha256(p) == hashlib.sha256(b"abc").hexdigest()


def test_verify_ok_and_missing(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    assert fw.verify(tmp_path) == []
    (tmp_path / "plda" / "plda.npz").unlink()
    assert fw.verify(tmp_path) == ["plda/plda.npz"]


def test_verify_detects_wrong_hash(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    (tmp_path / "config.yaml").write_bytes(b"tampered")
    assert fw.verify(tmp_path) == ["config.yaml"]


def test_main_valid_needs_no_token_or_network(tmp_path, monkeypatch):
    _write_valid(tmp_path, monkeypatch)
    monkeypatch.setattr(fw, "fetch", lambda *a, **k: pytest.fail("must not fetch"))
    monkeypatch.setattr(fw, "_token", lambda: pytest.fail("must not read a token"))
    assert fw.main([], dest=tmp_path) == 0


def test_main_without_token_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fw, "_token", lambda: "")
    assert fw.main([], dest=tmp_path) == 2
    assert "huggingface.co/pyannote/speaker-diarization-community-1" in capsys.readouterr().out


def test_main_fetches_then_verifies(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fw, "_token", lambda: "hf_x")

    def _fake_fetch(dest, token):
        calls.append(token)
        _write_valid(dest, monkeypatch)

    monkeypatch.setattr(fw, "fetch", _fake_fetch)
    assert fw.main([], dest=tmp_path) == 0
    assert calls == ["hf_x"]


def test_main_hash_mismatch_after_fetch_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "_token", lambda: "hf_x")
    monkeypatch.setattr(fw, "fetch", lambda dest, token: None)  # writes nothing
    assert fw.main([], dest=tmp_path) == 1
