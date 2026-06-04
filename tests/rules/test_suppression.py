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


def test_python_file_wide_suppression(tmp_path: Path):
    code = dedent("""\
        # odoo-doctor: disable-file=search-in-loop
        from odoo import models

        class X(models.Model):
            _name = "x"
            def bad(self):
                for r in self:
                    self.env["res.partner"].search([])
    """)
    f = tmp_path / "test.py"
    f.write_text(code)
    suppressions = scan_python_suppressions(f)
    assert (str(f), 0, "search-in-loop") in suppressions


def test_xml_file_wide_suppression(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <!-- odoo-doctor: disable-file=view-field-not-in-model -->
        <odoo>
            <field name="x_dynamic"/>
        </odoo>
    """)
    f = tmp_path / "views.xml"
    f.write_text(xml)
    suppressions = scan_xml_suppressions(f)
    assert (str(f), 0, "view-field-not-in-model") in suppressions


def test_file_wide_suppression_blocks_all_lines(tmp_path: Path):
    """Pipeline integration: file-wide suppression removes all matching diagnostics."""
    from odoo_doctor.core.pipeline import apply_inline_suppressions, normalize_diagnostics
    from odoo_doctor.core.diagnostics import Diagnostic

    f = tmp_path / "models" / "sale.py"
    f.parent.mkdir()
    f.write_text("")
    fp = str(f)

    diags = normalize_diagnostics([
        Diagnostic(
            module="m", file_path=fp, line=10, column=0,
            rule="search-in-loop", category="Performance", severity="error",
            tier="P1", source="native", confidence="high", title="t",
            message="m", help="h", odoo_version="17.0",
        ),
        Diagnostic(
            module="m", file_path=fp, line=50, column=0,
            rule="search-in-loop", category="Performance", severity="error",
            tier="P1", source="native", confidence="high", title="t",
            message="m", help="h", odoo_version="17.0",
        ),
    ])
    suppressions = {(fp, 0, "search-in-loop")}
    result = apply_inline_suppressions(diags, suppressions)
    assert len(result) == 0
