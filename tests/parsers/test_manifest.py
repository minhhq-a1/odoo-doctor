# tests/parsers/test_manifest.py
"""Tests for manifest parsing."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.parsers.manifest import parse_manifest


def test_parse_valid_manifest(sample_addon: Path):
    result = parse_manifest(sample_addon)
    assert result.name == "Sale Custom"
    assert result.version == "17.0.1.0.0"
    assert "sale" in result.depends
    assert "stock" in result.depends
    assert result.license == "LGPL-3"
    assert result.installable is True
    assert "security/ir.model.access.csv" in result.data


def test_parse_minimal_manifest(tmp_path: Path):
    mod = tmp_path / "minimal"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Min"}')
    result = parse_manifest(mod)
    assert result.name == "Min"
    assert result.depends == []
    assert result.data == []
    assert result.version is None
    assert result.license is None


def test_parse_missing_manifest(tmp_path: Path):
    result = parse_manifest(tmp_path)
    assert result is None
