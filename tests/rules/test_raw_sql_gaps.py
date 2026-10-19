"""raw-sql-string-interpolation gaps found by review (0.10.3): SQL(), cursors, DDL, unpacking."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from odoo_doctor.rules.security.raw_sql_interpolation import (
    check_raw_sql_interpolation,
)


def _lines(tmp_path: Path, src: str) -> list[int]:
    f = tmp_path / "models" / "m.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(src))
    return [d.line for d in check_raw_sql_interpolation(f, "m", "19.0")]


# -- (a) SQL() built from a dynamic string ------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        'SQL(f"SELECT 1 FROM t WHERE a = {x}")',
        'SQL("SELECT 1 FROM t WHERE a = " + x)',
        'SQL("SELECT 1 FROM t WHERE a = {}".format(x))',
        'SQL("SELECT 1 FROM t WHERE a = %s" % x)',
        'sql.SQL(f"SELECT 1 FROM t WHERE a = {x}")',
        'SQL(query=f"SELECT 1 FROM t WHERE a = {x}")',
    ],
)
def test_sql_wrapper_around_dynamic_string_is_flagged(tmp_path: Path, expr: str):
    src = f"""\
        class M:
            def f(self, x):
                self.env.cr.execute({expr})
        """
    assert _lines(tmp_path, src) == [3]


def test_sql_wrapper_via_variable_is_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, x):
                q = SQL(f"SELECT 1 FROM t WHERE a = {x}")
                self.env.cr.execute(q)
        """
    assert _lines(tmp_path, src) == [4]


@pytest.mark.parametrize(
    "expr",
    [
        'SQL("SELECT 1 FROM t WHERE a = %s", x)',
        'SQL("SELECT 1 FROM t WHERE a = %(a)s", a=x)',
        'SQL("SELECT 1")',
        'SQL("SELECT 1 FROM %s", SQL.identifier(x))',
        'SQL("SELECT 1 FROM {}").format(Identifier(x))',
        'sql.SQL("SELECT 1 FROM {}").format(sql.Identifier(x))',
        'SQL(" ").join([SQL("a = %s", x), SQL("b = 1")])',
        "SQL(x)",
    ],
)
def test_sql_wrapper_with_separate_params_is_silent(tmp_path: Path, expr: str):
    src = f"""\
        class M:
            def f(self, x):
                self.env.cr.execute({expr})
        """
    assert _lines(tmp_path, src) == []


# -- (b) cursor receivers ------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        "request.env.cr.execute(f'SELECT {x}')",
        "request.cr.execute(f'SELECT {x}')",
        "http.request.env.cr.execute(f'SELECT {x}')",
        "self.pool.cursor().execute(f'SELECT {x}')",
        "registry.cursor().execute(f'SELECT {x}')",
        "self.env.registry.cursor().execute(f'SELECT {x}')",
    ],
)
def test_more_cursor_receivers_are_flagged(tmp_path: Path, call: str):
    src = f"""\
        class C:
            def f(self, x):
                {call}
        """
    assert _lines(tmp_path, src) == [3]


@pytest.mark.parametrize(
    "head",
    [
        "with registry.cursor() as cur:",
        "with self.pool.cursor() as new_cr:",
        "with closing(self.pool.cursor()) as cur:",
    ],
)
def test_names_bound_to_a_cursor_are_flagged(tmp_path: Path, head: str):
    name = head.rsplit(" as ", 1)[1].rstrip(":")
    src = f"""\
        class C:
            def f(self, x):
                {head}
                    {name}.execute(f'SELECT {{x}}')
        """
    assert _lines(tmp_path, src) == [4]


def test_assigned_cursor_is_flagged(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                cur = self.pool.cursor()
                cur.execute(f'SELECT {x}')
        """
    assert _lines(tmp_path, src) == [4]


def test_parameterised_calls_on_new_receivers_are_silent(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                request.env.cr.execute("SELECT %s", (x,))
                with registry.cursor() as cur:
                    cur.execute("SELECT %s", (x,))
        """
    assert _lines(tmp_path, src) == []


def test_execute_on_a_non_cursor_stays_silent(tmp_path: Path):
    src = """\
        class C:
            def f(self, x, job, cur):
                job.execute(f"SELECT {x}")
                self.logger.execute(f"update the record {x}")
                cur.execute(f"SELECT {x}")
        """
    assert _lines(tmp_path, src) == []


# -- (c) statements beyond SELECT/INSERT/UPDATE/DELETE/CREATE -------------------------


@pytest.mark.parametrize(
    "template",
    [
        "DROP TABLE {}",
        "ALTER TABLE {} ADD COLUMN x int",
        "TRUNCATE {}",
        "WITH x AS (VALUES (1)) TABLE {}",
        "GRANT ALL ON {} TO PUBLIC",
        "COPY {} TO STDOUT",
        "create index on {} (id)",
        "  \n drop table {}",
        "SELECT * FROM {}",
        "INSERT INTO {} DEFAULT VALUES",
        "UPDATE {} SET a = 1",
        "DELETE FROM {}",
    ],
)
def test_ddl_and_other_statements_with_format_are_flagged(
    tmp_path: Path, template: str
):
    src = f"""\
        class C:
            def f(self, t):
                self.env.cr.execute({template!r}.format(t))
        """
    assert _lines(tmp_path, src) == [3]


def test_non_sql_format_text_is_silent(tmp_path: Path):
    src = """\
        class C:
            def f(self, t):
                self.env.cr.execute("hello {}".format(t))
                self.env.cr.execute("nothing to see here {}".format(t))
        """
    assert _lines(tmp_path, src) == []


# -- (d) tuple unpacking and walrus ----------------------------------------------------


def test_tuple_unpacking_carries_taint(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                a, b = "SELECT 1", f"SELECT {x}"
                self.env.cr.execute(b)
        """
    assert _lines(tmp_path, src) == [4]


def test_tuple_unpacking_keeps_safe_elements_safe(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                a, b = "SELECT 1", f"SELECT {x}"
                self.env.cr.execute(a)
                (c, d), e = ("SELECT 2", 1), 2
                self.env.cr.execute(c)
        """
    assert _lines(tmp_path, src) == []


def test_swap_does_not_lose_taint(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                a = "SELECT 1"
                b = f"SELECT {x}"
                a, b = b, a
                self.env.cr.execute(a)
        """
    assert _lines(tmp_path, src) == [6]


def test_walrus_carries_taint(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                if (q := f"SELECT {x}"):
                    self.env.cr.execute(q)
        """
    assert _lines(tmp_path, src) == [4]


def test_walrus_inline_in_call_is_flagged(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                self.env.cr.execute(q := "SELECT " + x)
        """
    assert _lines(tmp_path, src) == [3]


def test_walrus_constant_is_silent(tmp_path: Path):
    src = """\
        class C:
            def f(self, x):
                if (q := "SELECT 1 WHERE a = %s"):
                    self.env.cr.execute(q, (x,))
        """
    assert _lines(tmp_path, src) == []
