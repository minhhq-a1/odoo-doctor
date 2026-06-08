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
    assert len(diags) == 1


def test_search_in_loop_ignores_re_search(tmp_path):
    code = dedent("""\
        import re
        class X:
            def m(self, items):
                for s in items:
                    re.search(r"\\d+", s)
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    assert check_search_in_loop(f, "m", "17.0") == []


def test_search_in_loop_ignores_file_read(tmp_path):
    code = dedent("""\
        class X:
            def m(self, paths):
                for p in paths:
                    data = open(p).read()
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    assert check_search_in_loop(f, "m", "17.0") == []


def test_unbounded_search_in_controller_catches(tmp_path: Path):
    from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search

    code = dedent("""\
        from odoo import http

        class MyCtrl(http.Controller):
            @http.route("/all")
            def get_all(self):
                return http.request.env["res.partner"].search([])
    """)
    f = tmp_path / "c.py"
    f.write_text(code)
    diags = check_unbounded_search(f, "test_mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "unbounded-search"
    assert diags[0].severity == "warning"


def test_unbounded_search_in_compute_catches(tmp_path: Path):
    from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search

    code = dedent("""\
        from odoo import models, api

        class MyModel(models.Model):
            _name = "my.model"

            @api.depends("name")
            def _compute_foo(self):
                for rec in self:
                    rec.foo = self.env["res.partner"].search([])
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    diags = check_unbounded_search(f, "test_mod", "17.0")
    assert len(diags) == 1


def test_unbounded_search_with_limit_silent(tmp_path: Path):
    from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search

    code = dedent("""\
        from odoo import http

        class MyCtrl(http.Controller):
            @http.route("/some")
            def get_some(self):
                return http.request.env["res.partner"].search([], limit=10)
    """)
    f = tmp_path / "c.py"
    f.write_text(code)
    diags = check_unbounded_search(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_unbounded_search_outside_risky_context_silent(tmp_path: Path):
    from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search

    code = dedent("""\
        from odoo import models

        class MyModel(models.Model):
            _name = "my.model"

            def ordinary_method(self):
                return self.env["res.partner"].search([])
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    diags = check_unbounded_search(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_unbounded_search_ignores_re_search(tmp_path: Path):
    from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search

    code = dedent("""\
        from odoo import http
        import re

        class MyCtrl(http.Controller):
            @http.route("/match")
            def get_match(self):
                re.search([], "abc")
                return ""
    """)
    f = tmp_path / "c.py"
    f.write_text(code)
    diags = check_unbounded_search(f, "test_mod", "17.0")
    assert len(diags) == 0
