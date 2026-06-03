# tests/rules/test_suppression.py
"""Tests for inline suppression scanner."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.suppression import scan_python_suppressions, scan_xml_suppressions


def test_python_suppression(tmp_path: Path):
    code = dedent("""\
        x = 1
        # odoo-doctor: disable=search-in-loop
        for r in self:
            self.env["res.partner"].search([])
    """)
    f = tmp_path / "test.py"
    f.write_text(code)
    suppressions = scan_python_suppressions(f)
    assert (str(f), 3, "search-in-loop") in suppressions


def test_xml_suppression(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <!-- odoo-doctor: disable=view-field-not-in-model -->
            <field name="x_dynamic"/>
        </odoo>
    """)
    f = tmp_path / "views.xml"
    f.write_text(xml)
    suppressions = scan_xml_suppressions(f)
    assert any(rule == "view-field-not-in-model" for _, _, rule in suppressions)


def test_no_suppressions(tmp_path: Path):
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n")
    assert scan_python_suppressions(f) == set()
