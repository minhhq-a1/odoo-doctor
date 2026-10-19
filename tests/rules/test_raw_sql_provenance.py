"""raw-sql-string-interpolation: safe provenance, and which findings are `high`.

`high` is kept for SQL built from a parameter that a caller outside the module controls
(a public method is reachable by RPC, a route by HTTP). SQL built only from model
metadata or ORM-built fragments, or from the parameter of a `_private` helper, is the
pattern Odoo's own addons use: it is still listed, as `medium`.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from odoo_doctor.rules.security.raw_sql_interpolation import (
    check_raw_sql_interpolation,
)


def _found(tmp_path: Path, body: str) -> list[tuple[int, str]]:
    f = tmp_path / "models" / "m.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(body))
    return [(d.line, d.confidence) for d in check_raw_sql_interpolation(f, "m", "19.0")]


@pytest.mark.parametrize(
    "sql",
    [
        '"SELECT id FROM t LIMIT %d" % limit',
        '"SELECT id FROM t LIMIT %i" % limit',
        '"SELECT id FROM t WHERE x > %f" % limit',
        '"SELECT id FROM t LIMIT %d OFFSET %d" % (limit, limit)',
        '"SELECT id FROM %s LIMIT %d" % (self._table, limit)',
        '"SELECT id FROM t LIMIT %(n)d" % {"n": limit}',
        "'' if limit is None else ' LIMIT %d' % limit",
    ],
)
def test_numeric_percent_formats_cannot_inject(tmp_path: Path, sql: str):
    """`%d` of a non-number raises TypeError, it never writes text into the query."""
    src = f"""\
        class M:
            def f(self, limit):
                self.env.cr.execute({sql})
        """
    assert _found(tmp_path, src) == []


@pytest.mark.parametrize(
    "sql",
    [
        "\"SELECT id FROM t WHERE n = '%s' LIMIT %d\" % (name, limit)",
        "\"SELECT id FROM t WHERE n = '%s'\" % name",
        '"SELECT id FROM t LIMIT %s" % limit',
        '"SELECT id FROM t WHERE n = \'%(n)s\' LIMIT %(l)d" % {"n": name, "l": limit}',
    ],
)
def test_text_conversions_beside_numeric_ones_still_flag(tmp_path: Path, sql: str):
    src = f"""\
        class M:
            def f(self, name, limit):
                self.env.cr.execute({sql})
        """
    assert _found(tmp_path, src) == [(3, "high")]


def test_query_object_sql_is_safe(tmp_path: Path):
    """Odoo 14-17: `_where_calc(domain).get_sql()` and `query.select()/subselect()`."""
    src = """\
        class M:
            def a(self, domain):
                query = self._where_calc(domain)
                from_clause, where_clause, params = query.get_sql()
                self.env.cr.execute(f"SELECT id FROM {from_clause} WHERE {where_clause}", params)

            def b(self, domain):
                tables, where, params = self.env["x"]._where_calc(domain).get_sql()
                self.env.cr.execute("SELECT id FROM " + tables + " WHERE " + where, params)

            def c(self, domain):
                query = self._where_calc(domain)
                query_str, params = query.select("id", "SUM(x) AS total")
                self.env.cr.execute(f"SELECT * FROM ({query_str}) t", params)

            def d(self, domain):
                sql, params = self._where_calc(domain).subselect()
                self.env.cr.execute(f"SELECT * FROM t WHERE id IN {sql}", params)
        """
    assert _found(tmp_path, src) == []


def test_select_with_a_dynamic_column_is_not_safe(tmp_path: Path):
    src = """\
        class M:
            def f(self, domain, col):
                query_str, params = self._where_calc(domain).select(col)
                self.env.cr.execute(f"SELECT * FROM ({query_str}) t", params)
        """
    assert _found(tmp_path, src) == [(4, "high")]


def test_unpacking_an_unknown_call_stays_unknown(tmp_path: Path):
    src = """\
        class M:
            def f(self, domain):
                a, b = self._opaque(domain)
                self.env.cr.execute(f"SELECT {a}")
        """
    assert _found(tmp_path, src) == [(4, "high")]


@pytest.mark.parametrize(
    "guard",
    [
        "if operator not in ('<', '=', '>'):\n                    return []",
        "if operator not in ['<', '=', '>']:\n                    raise ValueError(operator)",
        "if operator not in {'<', '=', '>'}:\n                    return None",
    ],
)
def test_value_checked_against_literal_choices_is_a_constant(
    tmp_path: Path, guard: str
):
    src = f"""\
        class M:
            def f(self, operator):
                {guard}
                self.env.cr.execute(f"SELECT id FROM t WHERE x {{operator}} 1")
        """
    assert _found(tmp_path, src) == []


@pytest.mark.parametrize(
    "guard",
    [
        # the check does not stop the function
        "if operator not in ('<', '='):\n                    _logger.warning(operator)",
        # the choices are not constants
        "if operator not in self._operators:\n                    return []",
        # `in` keeps the bad branch alive
        "if operator in ('<', '='):\n                    return []",
        # the name is rebound after the check
        "if operator not in ('<', '='):\n                    return []\n                operator = operator + other",
    ],
)
def test_other_checks_prove_nothing(tmp_path: Path, guard: str):
    src = f"""\
        class M:
            def f(self, operator, other):
                {guard}
                self.env.cr.execute(f"SELECT id FROM t WHERE x {{operator}} 1")
        """
    assert [c for _, c in _found(tmp_path, src)] == ["high"]


def test_record_id_and_clock_values_are_not_text(tmp_path: Path):
    src = """\
        class M:
            def f(self, team):
                cond = f"team_id = {team.id} AND d > '{fields.Datetime.now()}'"
                self.env.cr.execute("SELECT 1 FROM crm_lead WHERE " + cond)
        """
    assert _found(tmp_path, src) == []


def test_public_method_parameter_is_high(tmp_path: Path):
    src = """\
        class M:
            def f(self, name):
                self.env.cr.execute(f"SELECT 1 WHERE n = '{name}'")
        """
    assert _found(tmp_path, src) == [(3, "high")]


def test_route_parameter_is_high_even_if_the_name_is_private(tmp_path: Path):
    src = """\
        class C:
            @http.route("/x", auth="public")
            def _hidden(self, name):
                request.env.cr.execute(f"SELECT 1 WHERE n = '{name}'")
        """
    assert _found(tmp_path, src) == [(4, "high")]


def test_parameter_reaches_sql_through_locals_and_closures(tmp_path: Path):
    src = """\
        class M:
            def f(self, name):
                parts = ["SELECT 1"]
                parts.append("WHERE n = '" + name + "'")
                self.env.cr.execute(" ".join(parts))

            def g(self, name):
                def run():
                    self.env.cr.execute(f"SELECT 1 WHERE n = '{name}'")
                run()
        """
    assert _found(tmp_path, src) == [(5, "high"), (9, "high")]


def test_parameter_beside_model_metadata_is_still_high(tmp_path: Path):
    """The metadata does not excuse the parameter written next to it."""
    src = """\
        class M:
            def f(self, name):
                self.env.cr.execute(f"SELECT {self._cols} FROM t WHERE n = '{name}'")
        """
    assert _found(tmp_path, src) == [(3, "high")]


@pytest.mark.parametrize(
    "src",
    [
        # private helper: its caller is inside the module
        """\
        class M:
            def _helper(self, column):
                self.env.cr.execute(f"UPDATE t SET {column} = 1")
        """,
        # model metadata and an ORM-built fragment, no parameter
        """\
        class M:
            def f(self):
                self.env.cr.execute(f"SELECT {self._sequence_field} FROM {self._table} {self._where()}")
        """,
        # a fragment method of the model, `%` with a dict
        """\
        class M:
            def f(self):
                join, where = self._extra()
                self.env.cr.execute("SELECT 1 FROM t %(j)s WHERE %(w)s" % {"j": join, "w": where})
        """,
        # a module-level helper
        """\
        def run(cr, table):
            cr.execute(f"DELETE FROM {table}")
        """,
        # the parameter only enters as an int
        """\
        class M:
            def f(self, n):
                self.env.cr.execute(f"SELECT {self._cols} LIMIT {int(n)}")
        """,
        # a public method whose parameter is only bound
        """\
        class M:
            def f(self, ids):
                self.env.cr.execute(f"SELECT {self._cols} FROM t WHERE id IN %s", (tuple(ids),))
        """,
    ],
)
def test_convention_pattern_is_medium(tmp_path: Path, src: str):
    assert [c for _, c in _found(tmp_path, src)] == ["medium"]


def test_variable_rebound_without_the_parameter_is_no_longer_caller_controlled(
    tmp_path: Path,
):
    """website_sale `shop`: `query` held a domain built from the route's input, then the SQL."""
    src = """\
        class C:
            def shop(self, search):
                query = self._where_calc(search)
                from_clause, where_clause, params = query.get_sql()
                query = f"SELECT {self.rate} FROM {from_clause} WHERE {where_clause}"
                self.env.cr.execute(query, params)
        """
    assert _found(tmp_path, src) == [(6, "medium")]


def test_parameter_passed_through_a_helper_into_sql_is_high(tmp_path: Path):
    src = """\
        class M:
            def f(self, name):
                where = self._clause(name)
                self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}")
        """
    assert _found(tmp_path, src) == [(4, "high")]


def test_with_target_inherits_the_state_of_its_context_manager(tmp_path: Path):
    """l10n_fr_fec: a cursor opened in `with` must not look like caller input."""
    src = """\
        class M:
            def f(self):
                with self.get_cursor() as cr:
                    lang = self.env.with_env(cr).user.lang
                    self.env.cr.execute(f"SELECT name->>'{lang}' FROM t")
        """
    assert _found(tmp_path, src) == [(5, "medium")]
