"""expensive-nonstored-compute flags non-stored computes that query the ORM."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.expensive_nonstored_compute import (
    check_expensive_nonstored_compute,
)


def _run(tmp_path: Path, src: str):
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return check_expensive_nonstored_compute(f, "m", "17.0")


def test_nonstored_compute_with_search_count_is_flagged(tmp_path: Path):
    diags = _run(
        tmp_path,
        """\
        class P(models.Model):
            total = fields.Integer(compute="_compute_total")

            def _compute_total(self):
                for rec in self:
                    rec.total = self.env["sale.order"].search_count([])
        """,
    )
    assert [d.rule for d in diags] == ["expensive-nonstored-compute"]
    d = diags[0]
    assert d.line == 2
    assert d.confidence == "medium" and d.tier == "P2"
    assert "total" in d.title and "search_count" in d.message


def test_stored_compute_is_not_flagged(tmp_path: Path):
    assert not _run(
        tmp_path,
        """\
        class P(models.Model):
            total = fields.Integer(compute="_compute_total", store=True)

            def _compute_total(self):
                self.total = self.env["x"].search_count([])
        """,
    )


def test_explicit_store_false_is_flagged(tmp_path: Path):
    assert _run(
        tmp_path,
        """\
        class P(models.Model):
            total = fields.Integer(compute="_c", store=False)

            def _c(self):
                self.total = len(self.search([]))
        """,
    )


def test_compute_without_query_is_not_flagged(tmp_path: Path):
    assert not _run(
        tmp_path,
        """\
        class P(models.Model):
            total = fields.Integer(compute="_c")

            @api.depends("line_ids.qty")
            def _c(self):
                for rec in self:
                    rec.total = sum(rec.line_ids.mapped("qty"))
        """,
    )


def test_non_orm_search_receiver_is_not_flagged(tmp_path: Path):
    assert not _run(
        tmp_path,
        """\
        import re

        class P(models.Model):
            flag = fields.Boolean(compute="_c")

            def _c(self):
                for rec in self:
                    rec.flag = bool(re.search("x", rec.name or ""))
        """,
    )


def test_missing_compute_method_and_syntax_error_are_safe(tmp_path: Path):
    assert not _run(
        tmp_path,
        """\
        class P(models.Model):
            total = fields.Integer(compute="_missing")
        """,
    )
    assert not _run(tmp_path, "def broken(:\n")
