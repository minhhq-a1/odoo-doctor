# tests/adapters/test_ruff.py
"""Tests for Ruff adapter."""

from __future__ import annotations

import json
from pathlib import Path

from odoo_doctor.adapters.base import BackendAdapter
from odoo_doctor.adapters.ruff.adapter import RuffAdapter


def test_ruff_adapter_is_backend_adapter():
    adapter = RuffAdapter()
    assert adapter.name == "ruff"


def test_ruff_adapter_parse_output(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "ruff" for d in diags)
    assert diags[0].rule == "E501"


def test_ruff_adapter_applies_rule_mapping(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    e501 = next(d for d in diags if d.rule == "E501")
    assert e501.category == "Maintainability"
    assert e501.tier == "P3"


def test_ruff_adapter_unmapped_rule():
    adapter = RuffAdapter()
    raw = [{"code": "UNKNOWN999", "message": "something", "filename": "f.py",
            "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 1}}]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].tier == "P3"
    assert diags[0].confidence == "low"


def test_ruff_adapter_filters_f401_in_init():
    adapter = RuffAdapter()
    raw = [
        {"code": "F401", "message": "unused import", "filename": "__init__.py",
         "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 1}},
        {"code": "F401", "message": "unused import", "filename": "models/res_partner.py",
         "location": {"row": 5, "column": 1}, "end_location": {"row": 5, "column": 1}},
    ]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    # F401 in __init__.py is filtered out, but the one in res_partner.py is kept
    assert len(diags) == 1
    assert diags[0].file_path == "models/res_partner.py"
