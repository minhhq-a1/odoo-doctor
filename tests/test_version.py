"""One version everywhere: pyproject, package, JSON report."""

from __future__ import annotations

import re
from pathlib import Path

from odoo_doctor import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
    assert __version__ == declared


def test_changelog_has_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
