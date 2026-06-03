# tests/discovery/test_odoo_version.py
"""Tests for Odoo version detection."""

from __future__ import annotations

from odoo_doctor.discovery.odoo_version import detect_odoo_version


def test_cli_flag_wins():
    assert detect_odoo_version(cli_version="16.0", config_version="17.0", manifest_version="15.0.1.0.0") == "16.0"


def test_config_fallback():
    assert detect_odoo_version(cli_version=None, config_version="17.0", manifest_version=None) == "17.0"


def test_manifest_prefix():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="17.0.1.0.0") == "17.0"


def test_manifest_short():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="16.0") == "16.0"


def test_unknown():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version=None) == "unknown"


def test_non_standard_manifest_version():
    """Custom version strings should not be treated as Odoo version."""
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="2.3.1") == "unknown"
