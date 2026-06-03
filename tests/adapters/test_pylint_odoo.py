# tests/adapters/test_pylint_odoo.py
"""Tests for Pylint-Odoo adapter."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter


def test_pylint_adapter_name():
    adapter = PylintOdooAdapter()
    assert adapter.name == "pylint-odoo"


def test_pylint_parse_output(fixtures_dir: Path):
    adapter = PylintOdooAdapter()
    raw_text = (fixtures_dir / "adapters" / "pylint_odoo_output.txt").read_text()
    diags = adapter._parse_output(raw_text, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "pylint-odoo" for d in diags)

    sql = next(d for d in diags if d.rule == "E8102")
    assert sql.category == "Security"
    assert sql.tier == "P0"

    trans = next(d for d in diags if d.rule == "W8120")
    assert trans.category == "Maintainability"


def test_pylint_unmapped_rule():
    adapter = PylintOdooAdapter()
    raw_text = "f.py:1:0: C9999: Unknown rule (unknown-rule)\n"
    diags = adapter._parse_output(raw_text, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].confidence == "low"
