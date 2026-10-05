"""CampaignScribe is licensed GPL-3.0-only, copyright Imagination Industries LLC."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import app

ROOT = Path(__file__).resolve().parents[2]
# sha256 of https://www.gnu.org/licenses/gpl-3.0.txt (canonical GPL v3 text)
GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def test_license_file_is_canonical_gpl3():
    data = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == GPL3_SHA256


def test_pyproject_declares_gpl3_only():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["license"] == "GPL-3.0-only"
    assert meta["license-files"] == ["LICENSE"]


def test_package_constants():
    assert app.LICENSE_SPDX == "GPL-3.0-only"
    assert app.COPYRIGHT_NOTICE == "Copyright (C) 2026 Imagination Industries LLC"


def test_readme_and_about_carry_the_notice():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## License" in readme and "GPL-3.0-only" in readme
    assert "Imagination Industries LLC" in readme
    about = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    assert "COPYRIGHT_NOTICE" in about and "GPL-3.0-only" in about
