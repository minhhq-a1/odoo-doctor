# tests/rules/test_performance_rules.py
"""Tests for performance rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.search_in_loop import check_search_in_loop


def test_search_in_loop_catches(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def bad_method(self):
                for rec in self:
                    partner = self.env["res.partner"].search([("name", "=", rec.name)])
    """)
    f = tmp_path / "bad.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) >= 1
    assert diags[0].rule == "search-in-loop"


def test_search_in_loop_clean(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def good_method(self):
                partners = self.env["res.partner"].search([("active", "=", True)])
                for p in partners:
                    print(p.name)
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_search_in_loop_nested(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def nested(self):
                for order in self:
                    for line in order.order_line:
                        self.env["product.product"].browse(line.product_id.id)
    """)
    f = tmp_path / "nested.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) >= 1
