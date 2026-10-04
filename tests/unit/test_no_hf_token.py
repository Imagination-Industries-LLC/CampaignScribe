"""No HuggingFace token remains anywhere in the app or user-facing docs."""

from __future__ import annotations

import re
from pathlib import Path

from app import config

ROOT = Path(__file__).resolve().parents[2]


def test_config_has_no_token_api():
    assert not hasattr(config, "get_huggingface_token")
    assert not hasattr(config, "save_huggingface_token")


def test_no_token_api_left():
    pat = re.compile(
        r"get_huggingface_token|save_huggingface_token|hf_token|HuggingFace token", re.I
    )
    hits = []
    for p in (ROOT / "app").rglob("*.py"):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert hits == []
