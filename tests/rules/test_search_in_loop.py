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


def test_comprehension_runs_its_element_once_per_item(tmp_path: Path):
    src = """\
        class A:
            def f(self, recs):
                a = [self.env["x"].search([("a", "=", r.id)]) for r in recs]
                b = {r: self.env["x"].search([("a", "=", r.id)]) for r in recs}
                c = list(self.env["x"].search([("a", "=", r.id)]) for r in recs)
                d = {self.env["x"].search_count([("a", "=", r.id)]) for r in recs}
                e = [r for r in recs if self.env["x"].search([("a", "=", r.id)])]
                return a, b, c, d, e
        """
    assert _lines(tmp_path, src) == [3, 4, 5, 6, 7]


def test_first_iterable_of_a_comprehension_runs_once(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                a = [r.name for r in self.env["x"].search([])]
                b = [c for r in self for c in self.env["x"].search([("a", "=", r.id)])]
                return a, b
        """
    assert _lines(tmp_path, src) == [4]


def test_comprehension_over_a_literal_of_constants_is_bounded(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                return [self.env[m].search_count([]) for m in ("a.b", "c.d")]
        """
    assert _lines(tmp_path, src) == []


def test_comprehension_in_a_loop_is_reported_once(tmp_path: Path):
    src = """\
        class A:
            def f(self, recs):
                for a in recs:
                    [self.env["x"].search([("a", "=", c)]) for c in a.ids]
        """
    assert _lines(tmp_path, src) == [4]


def test_search_read_read_group_and_search_fetch_are_orm_queries(tmp_path: Path):
    src = """\
        class A:
            def f(self, recs):
                for r in recs:
                    self.env["x"].search_read([("a", "=", r.id)])
                    self.env["x"].read_group([("a", "=", r.id)], ["a"], ["a"])
                    self.env["x"]._read_group([("a", "=", r.id)], ["a"])
                    self.env["x"].search_fetch([("a", "=", r.id)], ["a"])
        """
    assert _lines(tmp_path, src) == [4, 5, 6, 7]


def test_attribute_set_in_init_is_not_a_recordset(tmp_path: Path):
    src = """\
        class Service:
            client = None

            def __init__(self, client):
                self.api = client

            def f(self, names):
                for n in names:
                    self.client.search(n)
                    self.api.search(n)
        """
    assert _lines(tmp_path, src) == []


def test_field_assigned_on_self_is_still_a_recordset(tmp_path: Path):
    src = """\
        from odoo import fields, models


        class A(models.Model):
            _name = "a"
            line_ids = fields.One2many("a.line", "a_id")

            def f(self, names):
                for n in names:
                    self.line_ids.search([("name", "=", n)])
                    self.partner_id.search([("name", "=", n)])
        """
    assert _lines(tmp_path, src) == [10, 11]


def test_local_recordset_iterated_later_is_a_recordset(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                recs = self.env["x"].search([])
                for rec in recs:
                    rec.search([("a", "=", rec.id)])
        """
    assert _lines(tmp_path, src) == [5]


def test_local_that_is_not_a_recordset_stays_silent(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                groups = self.env["x"].read_group([], ["a"], ["a"])
                total = self.env["x"].search_count([])
                for g in groups:
                    g.search("x")
                for t in total:
                    t.search("x")
        """
    assert _lines(tmp_path, src) == []


def test_local_recordset_is_scoped_to_its_function(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                recs = self.env["x"].search([])

            def g(self, recs):
                for rec in recs:
                    rec.search([("a", "=", rec.id)])
        """
    assert _lines(tmp_path, src) == []


def _tiers(tmp_path: Path, src: str) -> list[tuple[int, str]]:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return [(d.line, d.confidence) for d in check_search_in_loop(f, "m", "19.0")]


def test_only_a_query_the_loop_cannot_change_is_high(tmp_path: Path):
    """Odoo's own addons query per record (hundreds of times in core 19): medium. High
    needs a query that is a plain statement of the body and does not use the loop."""
    src = """\
        class A:
            def f(self, vals):
                for rec in self:
                    self.env["x"].search([("a", "=", rec.id)])
                    self.env["x"].search([("a", "=", 1)])
                    self.env["x"].search_count([("a", "=", self.id)])
                    self.env["x"].search_read([("a", "=", 1)])
                    self.env["x"]._read_group([("a", "=", 1)], ["a"])
                    if rec.a:
                        self.env["x"].search([("a", "=", 1)])
                recs = self.env["x"].search([])
                for r in recs:
                    r.search([("a", "=", 1)])
                    self.env["x"].search([("a", "=", 1)])
                [self.env["x"].search([("a", "=", 1)]) for v in vals]
        """
    assert _tiers(tmp_path, src) == [
        (4, "medium"),
        (5, "high"),
        (6, "high"),
        (7, "medium"),
        (8, "medium"),
        (10, "medium"),
        (13, "medium"),
        (14, "high"),
        (15, "medium"),
    ]


def test_a_loop_that_writes_or_rebinds_keeps_a_query_medium(tmp_path: Path):
    src = """\
        class A:
            def f(self, names):
                for rec in self:
                    self.env["x"].search([("a", "=", 1)])
                    rec.write({"a": 1})
                for name in names:
                    self.env["x"].search([("a", "=", 1)])
                    self.env["x"].search([("a", "=", name)])
                domain = []
                for name in names:
                    domain.append(("a", "=", name))
                    self.env["x"].search(domain)
                while names:
                    self.env["x"].search([("a", "=", 1)])
                for a in names:
                    for b in names:
                        self.env["x"].search([("a", "=", a)])
        """
    assert _tiers(tmp_path, src) == [
        (4, "medium"),
        (7, "high"),
        (8, "medium"),
        (12, "medium"),
        (14, "medium"),
        (17, "medium"),
    ]


def test_rebinding_self_or_a_loop_variable_keeps_the_plain_tier(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                self = self.with_context(a=1)
                task = self.env["x"].browse(1)
                for task in self:
                    task.search([("a", "=", task.id)])
                for rec in self:
                    self.env["x"].search([("a", "=", 1)])
        """
    assert _tiers(tmp_path, src) == [(6, "medium"), (8, "high")]


def test_env_lookup_on_a_local_adapter_of_self_stays_high(tmp_path: Path):
    src = """\
        class A:
            def f(self):
                ctx = self.with_context(a=1)
                for rec in self:
                    ctx.env["x"].search([("a", "=", 1)])
                    ctx.search([("a", "=", 1)])
        """
    assert _tiers(tmp_path, src) == [(5, "high"), (6, "medium")]


def test_comprehension_nested_in_a_loop_is_medium(tmp_path: Path):
    src = """\
        class A:
            def f(self, recs):
                for r in self.env["x"].search([]):
                    [self.env["y"].search([("a", "=", i)]) for i in r.ids]
                for r in recs:
                    [self.search([("a", "=", i)]) for i in range(3)]
                while recs:
                    [self.search([("a", "=", q)]) for q in (1, 2, 3)]
        """
    assert _tiers(tmp_path, src) == [(4, "medium"), (6, "medium"), (8, "medium")]


def test_standalone_comprehension_is_medium_and_bounded_one_is_silent(tmp_path: Path):
    src = """\
        class A:
            def f(self, recs):
                a = [self.search([("a", "=", r)]) for r in recs]
                b = [self.search([("a", "=", q)]) for q in (1, 2, 3)]
                return a, b
        """
    assert _tiers(tmp_path, src) == [(3, "medium")]


def test_local_from_a_self_method_that_is_not_orm_is_not_a_recordset(tmp_path: Path):
    src = """\
        class A:
            def f(self, lines):
                rx = self._get_regex()
                for line in lines:
                    rx.search(line)
        """
    assert _tiers(tmp_path, src) == []
