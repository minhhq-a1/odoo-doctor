# tests/discovery/test_addons.py
"""Tests for addon discovery."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.discovery.addons import discover_addons


def test_discover_single_addon(sample_addon: Path):
    addons = discover_addons([sample_addon])
    assert len(addons) == 1
    assert addons[0].name == "sample_addon"
    assert addons[0].path == sample_addon


def test_discover_filters_by_target(sample_addon: Path):
    addons = discover_addons([sample_addon], target_modules=["nonexistent"])
    assert len(addons) == 0


def test_discover_empty_directory(tmp_path: Path):
    addons = discover_addons([tmp_path])
    assert addons == []


def test_discover_skips_non_installable(tmp_path: Path):
    mod = tmp_path / "disabled_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Disabled", "installable": False}')
    addons = discover_addons([tmp_path])
    assert len(addons) == 0


def test_discover_addons_tolerates_non_utf8_manifest(tmp_path):
    from odoo_doctor.discovery.addons import discover_addons

    addon = tmp_path / "mod"
    addon.mkdir()
    (addon / "__manifest__.py").write_bytes(b"{'name': '\xe9', 'installable': True}\n")
    # Must not raise; the addon is discovered (replaced char) rather than crashing
    result = discover_addons([tmp_path])
    assert len(result) == 1

