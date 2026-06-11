"""Test for create-in-loop and write-in-loop rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.create_write_in_loop import (
    check_create_write_in_loop,
)


def test_create_in_loop_catches(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def bad_method(self, vals_list):
                for vals in vals_list:
                    self.env["res.partner"].create(vals)
    """)
    f = tmp_path / "bad.py"
    f.write_text(code)
    diags = check_create_write_in_loop(f, "test_mod", "17.0")
    assert any(d.rule == "create-in-loop" for d in diags)


def test_write_in_loop_catches(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def bad_method(self):
                for rec in self:
                    rec.write({"name": "foo"})
    """)
    f = tmp_path / "bad.py"
    f.write_text(code)
    diags = check_create_write_in_loop(f, "test_mod", "17.0")
    assert any(d.rule == "write-in-loop" for d in diags)


def test_create_write_batch_is_clean(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def good_method(self, vals_list):
                self.env["res.partner"].create(vals_list)
                self.write({"name": "foo"})
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_create_write_in_loop(f, "test_mod", "17.0")
    assert len(diags) == 0
