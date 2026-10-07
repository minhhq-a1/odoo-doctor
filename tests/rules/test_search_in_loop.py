"""search-in-loop flags ORM calls evaluated once per iteration, not the loop's own setup."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.search_in_loop import check_search_in_loop


def _lines(tmp_path: Path, src: str, name: str = "m.py") -> list[int]:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(src))
    return [d.line for d in check_search_in_loop(f, "m", "19.0")]


def test_search_in_the_loop_body_is_flagged(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                for rec in self:
                    self.env["x"].search([("a", "=", rec.id)])
        """
    assert _lines(tmp_path, src) == [4]


def test_the_iterable_is_evaluated_once_and_is_not_in_the_loop(tmp_path: Path):
    """`for rec in self.env[...].search(...)` is the most common line in Odoo."""
    src = """\
        class A:
            def f(self):
                for rec in self.env["x"].search([]):
                    rec.name
        """
    assert _lines(tmp_path, src) == []


def test_iterable_of_an_inner_loop_runs_once_per_outer_iteration(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                for a in self:
                    for c in self.env["x"].search([("a", "=", a.id)]):
                        c.name
        """
    assert _lines(tmp_path, src) == [4]


def test_for_else_clause_runs_once(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                for a in self:
                    a.name
                else:
                    self.env["x"].search([])
        """
    assert _lines(tmp_path, src) == []


def test_while_condition_runs_every_iteration(tmp_path: Path):
    src = """\
        class A:
            def f(self, name):
                while self.search_count([("name", "=", name)]) > 0:
                    name += "x"
        """
    assert _lines(tmp_path, src) == [3]


def test_batched_while_loop_with_a_limit_is_the_remedy_not_the_problem(tmp_path: Path):
    src = """\
        class A:
            def cron(self):
                while True:
                    jobs = self.search([("state", "=", "done")], limit=1000)
                    if not jobs:
                        break
                    jobs.unlink()
        """
    assert _lines(tmp_path, src) == []


def test_while_loop_with_limit_one_is_still_a_lookup_per_iteration(tmp_path: Path):
    src = """\
        class A:
            def f(self, node):
                while node:
                    node = self.search([("parent_id", "=", node.id)], limit=1)
        """
    assert _lines(tmp_path, src) == [4]


def test_loop_over_chunks_runs_once_per_chunk(tmp_path: Path):
    src = """\
        from odoo.tools import split_every


        class A:
            def f(self, ids):
                for chunk in split_every(100, ids):
                    self.search([("id", "in", chunk)])
                for i in range(0, len(ids), 1000):
                    self.search([("id", "in", ids[i : i + 1000])])
        """
    assert _lines(tmp_path, src) == []


def test_range_without_a_step_is_still_a_loop_per_item(tmp_path: Path):
    src = """\
        class A:
            def f(self, ids):
                for i in range(len(ids)):
                    self.search([("id", "=", ids[i])])
        """
    assert _lines(tmp_path, src) == [4]


def test_loop_over_a_fixed_literal_does_not_scale_with_data(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                for model in ("sale.order", "purchase.order"):
                    self.env[model].search_count([])
        """
    assert _lines(tmp_path, src) == []


def test_loop_over_a_literal_of_expressions_is_still_flagged(tmp_path: Path):
    src = """\
        class A:
            def f(self, a, b):
                for x in (a, b):
                    self.search([("id", "=", x)])
        """
    assert _lines(tmp_path, src) == [4]
