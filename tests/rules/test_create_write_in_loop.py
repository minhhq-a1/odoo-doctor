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


def test_iterable_of_a_loop_is_not_inside_the_loop(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text(
        "class A:\n"
        "    def f(self, vals):\n"
        "        for rec in self.create(vals):\n"
        "            rec.name\n"
    )
    assert check_create_write_in_loop(f, "m", "19.0") == []


def _create_write(tmp_path: Path, src: str) -> list[tuple[str, int]]:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return [(d.rule, d.line) for d in check_create_write_in_loop(f, "m", "19.0")]


def test_create_in_a_comprehension_is_a_create_per_item(tmp_path: Path):
    src = """\
        class A:
            def f(self, vals_list):
                a = [self.env["x"].create(v) for v in vals_list]
                b = list(rec.write({"a": 1}) for rec in self)
                return a, b
        """
    assert _create_write(tmp_path, src) == [("create-in-loop", 3), ("write-in-loop", 4)]


def test_attribute_set_in_init_is_not_a_recordset(tmp_path: Path):
    src = """\
        class Service:
            def __init__(self, client):
                self.client = client

            def f(self, items):
                for i in items:
                    self.client.create(i)
                    self.client.write(i)
        """
    assert _create_write(tmp_path, src) == []


def test_write_on_a_local_recordset_is_a_write_per_record(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                recs = self.env["x"].search([])
                for rec in recs:
                    rec.write({"a": 1})
        """
    assert _create_write(tmp_path, src) == [("write-in-loop", 5)]
