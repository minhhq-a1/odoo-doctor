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


def test_inferred_receivers_are_medium(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text(
        dedent("""\
        class A:
            def f(self, vals_list):
                for rec in self:
                    rec.write({"a": 1})
                recs = self.env["x"].search([])
                for r in recs:
                    r.write({"a": 1})
                [self.env["x"].create(v) for v in vals_list]
        """)
    )
    diags = check_create_write_in_loop(f, "m", "19.0")
    assert [(d.rule, d.line, d.confidence) for d in diags] == [
        ("create-in-loop", 8, "medium"),
        ("write-in-loop", 4, "high"),
        ("write-in-loop", 7, "medium"),
    ]


def test_only_a_write_or_create_the_loop_does_not_feed_is_high(tmp_path: Path):
    """Per-record writes are everywhere in core 19: medium. High is `recs.write(vals)` in
    disguise, a lone statement whose values and context do not use the loop."""
    f = tmp_path / "m.py"
    f.write_text(
        dedent("""\
        class A:
            def f(self, names):
                for rec in self:
                    rec.write({"state": "done"})
                for rec in self:
                    rec.write({"name": rec.name})
                for rec in self:
                    rec.with_context(a=rec.id).write({"state": "done"})
                for rec in self:
                    rec.write({"state": "done"})
                    rec.message_post(body="x")
                for rec in self:
                    if rec.a:
                        rec.write({"state": "done"})
                for name in names:
                    self.env["x"].create({"a": 1})
                for name in names:
                    self.env["x"].create({"a": name})
                for name in names:
                    self.env["x"].with_context(a=name).create({"a": 1})
        """)
    )
    diags = check_create_write_in_loop(f, "m", "19.0")
    assert [(d.rule, d.line, d.confidence) for d in diags] == [
        ("create-in-loop", 16, "high"),
        ("create-in-loop", 18, "medium"),
        ("create-in-loop", 20, "medium"),
        ("write-in-loop", 4, "high"),
        ("write-in-loop", 6, "medium"),
        ("write-in-loop", 8, "medium"),
        ("write-in-loop", 10, "medium"),
        ("write-in-loop", 14, "medium"),
    ]
