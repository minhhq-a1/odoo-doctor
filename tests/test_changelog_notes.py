"""scripts/changelog_notes.py: the Release body is the CHANGELOG section of that version."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "changelog_notes", ROOT / "scripts" / "changelog_notes.py"
)
changelog_notes = importlib.util.module_from_spec(_SPEC)
sys.modules["changelog_notes"] = changelog_notes
_SPEC.loader.exec_module(changelog_notes)

CHANGELOG = """# Changelog

---

## [Unreleased]

---

## [1.2.0] — 2026-01-02

### Added

- new thing

---

## [1.1.0] — 2026-01-01

- old thing
"""


def test_returns_only_the_requested_section():
    assert changelog_notes.notes(CHANGELOG, "1.2.0") == "### Added\n\n- new thing"
    assert changelog_notes.notes(CHANGELOG, "1.1.0") == "- old thing"


def test_missing_or_empty_entry_is_empty():
    assert changelog_notes.notes(CHANGELOG, "9.9.9") == ""
    assert changelog_notes.notes(CHANGELOG, "1") == ""
    assert changelog_notes.notes(CHANGELOG, "Unreleased") == ""


def test_the_current_version_has_notes():
    from odoo_doctor import __version__

    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog_notes.notes(text, __version__)
