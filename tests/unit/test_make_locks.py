"""make_locks: render() filtering/normalisation/validation and lock_sha256 (pure, no venv)."""

from __future__ import annotations

import pytest

from scripts import make_locks as ml

GPU_FREEZE = [
    "torch==2.11.0+cu128",
    "torchaudio==2.11.0+cu128",
    "whisperx==3.8.6",
    "pyannote.audio==4.0.4",
    "faster-whisper==1.2.1",
    "Some_Pkg.Name==1.0",
    "anthropic==1.2.3",
    "pip==25.0",
    "setuptools==80.0",
    "wheel==0.45",
    "torchvision==0.23.0",
    "pytest==9.1.1",
]


def _render(freeze=None, **kw):
    args = {
        "profile": "gpu",
        "python_version": "3.13.16",
        "pip_version": "25.0",
        "dev_only": {"pytest"},
        "date": "2026-10-05",
    }
    args.update(kw)
    return ml.render(freeze if freeze is not None else GPU_FREEZE, **args)


def _pkg_lines(text):
    return [ln for ln in text.splitlines() if ln and not ln.startswith(("#", "--"))]


def test_header_and_index_line_gpu():
    lines = _render().splitlines()
    assert lines[0] == "# CampaignScribe gpu lock — Python 3.13.16 — generated 2026-10-05"
    assert lines[1] == "# pip==25.0"
    assert lines[2] == "--extra-index-url https://download.pytorch.org/whl/cu128"


def test_cpu_profile_index_and_validation():
    freeze = [ln.replace("cu128", "cpu") for ln in GPU_FREEZE]
    out = _render(freeze, profile="cpu")
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in out.splitlines()
    assert "torch==2.11.0+cpu" in out


def test_filtering():
    pkgs = _pkg_lines(_render())
    names = {p.split("==")[0] for p in pkgs}
    assert not names & {"pip", "setuptools", "wheel", "torchvision", "pytest"}
    assert {"torch", "torchaudio", "whisperx", "anthropic"} <= names


def test_normalisation_and_sorting():
    pkgs = _pkg_lines(_render())
    assert "some-pkg-name==1.0" in pkgs
    assert "pyannote-audio==4.0.4" in pkgs
    assert pkgs == sorted(pkgs)


def test_ends_with_newline_lf_only():
    out = _render()
    assert out.endswith("\n")
    assert "\r" not in out


def test_deterministic():
    assert _render() == _render(list(reversed(GPU_FREEZE)))


def test_gpu_rejects_cpu_torch():
    bad = [ln.replace("torch==2.11.0+cu128", "torch==2.11.0+cpu") for ln in GPU_FREEZE]
    with pytest.raises(ValueError, match="cu128"):
        _render(bad)


def test_gpu_rejects_cpu_torchaudio():
    bad = [ln.replace("torchaudio==2.11.0+cu128", "torchaudio==2.11.0") for ln in GPU_FREEZE]
    with pytest.raises(ValueError, match="torchaudio"):
        _render(bad)


def test_cpu_rejects_cuda_torch():
    with pytest.raises(ValueError, match="cpu"):
        _render(GPU_FREEZE, profile="cpu")


@pytest.mark.parametrize("missing", ["whisperx", "pyannote.audio", "torch", "faster-whisper"])
def test_requires_core_packages(missing):
    bad = [ln for ln in GPU_FREEZE if not ln.lower().startswith(missing + "==")]
    with pytest.raises(ValueError, match="missing"):
        _render(bad)


def test_unknown_profile():
    with pytest.raises(ValueError, match="profile"):
        _render(profile="tpu")


def test_lock_sha256_crlf_equals_lf(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"x==1\ny==2\n")
    b.write_bytes(b"x==1\r\ny==2\r\n")
    assert ml.lock_sha256(a) == ml.lock_sha256(b)
    b.write_bytes(b"x==1\r\ny==3\r\n")
    assert ml.lock_sha256(a) != ml.lock_sha256(b)
