# tests/core/test_config.py
"""Tests for config loading from odoo-doctor.toml."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.core.config import OdooDoctorConfig, load_config


def test_default_config():
    cfg = OdooDoctorConfig()
    assert cfg.odoo_version is None
    assert cfg.addons_paths == ["."]
    assert cfg.adapters["ruff"] is True
    assert cfg.adapters["pylint_odoo"] is True
    assert cfg.adapters["oca"] is False
    assert cfg.min_score == 0
    assert cfg.severity_overrides == {}
    assert cfg.ignore_rules == []
    assert cfg.ignore_files == []
    assert cfg.ignore_modules == []
    assert cfg.category_weights == {}


def test_load_config_from_toml(tmp_path: Path):
    toml_content = dedent("""\
        [odoo-doctor]
        odoo_version = "17.0"
        addons_paths = ["addons"]
        min_score = 60
        odoo_source_path = "/opt/odoo/src"

        [adapters]
        ruff = true
        pylint_odoo = false
        oca = false

        [severity]
        "search-in-loop" = "warning"

        [ignore]
        rules = ["deprecated-api"]
        files = ["**/migrations/**"]
        modules = ["legacy"]

        [category_weights]
        Security = 1.5
        "Module Hygiene" = 0.5
    """)
    config_file = tmp_path / "odoo-doctor.toml"
    config_file.write_text(toml_content)

    cfg = load_config(tmp_path)
    assert cfg.odoo_version == "17.0"
    assert cfg.addons_paths == ["addons"]
    assert cfg.min_score == 60
    assert cfg.odoo_source_path == "/opt/odoo/src"
    assert cfg.adapters["pylint_odoo"] is False
    assert cfg.severity_overrides == {"search-in-loop": "warning"}
    assert cfg.ignore_rules == ["deprecated-api"]
    assert cfg.ignore_files == ["**/migrations/**"]
    assert cfg.ignore_modules == ["legacy"]
    assert cfg.category_weights["Security"] == 1.5
    assert cfg.category_weights["Module Hygiene"] == 0.5


def test_load_config_missing_file(tmp_path: Path):
    cfg = load_config(tmp_path)
    assert cfg == OdooDoctorConfig()
