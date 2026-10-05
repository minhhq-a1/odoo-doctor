"""Taint-aware behaviour of raw-sql-string-interpolation and eval-usage (0.6.0).

The rules follow values through local variables, lists, branches and module
constants: provably constant SQL is not reported (fewer false positives) and
dynamic SQL built through containers/branches is (fewer false negatives).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.security.eval_usage import check_eval_usage
from odoo_doctor.rules.security.raw_sql_interpolation import (
    check_raw_sql_interpolation,
)


def _sql(tmp_path: Path, code: str):
    f = tmp_path / "m.py"
    f.write_text(dedent(code))
    return check_raw_sql_interpolation(f, "mod", "17.0")


def _eval(tmp_path: Path, code: str):
    f = tmp_path / "m.py"
    f.write_text(dedent(code))
    return check_eval_usage(f, "mod", "17.0")


# --- raw-sql: provably safe constructions are not reported --------------------


def test_placeholder_join_variable_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, ids):
                placeholders = ",".join(["%s"] * len(ids))
                self.env.cr.execute(f"SELECT 1 FROM t WHERE id IN ({placeholders})", ids)
            """,
        )
        == []
    )


def test_inline_placeholder_join_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, ids):
                self.env.cr.execute(
                    f"SELECT 1 FROM t WHERE id IN ({', '.join(['%s'] * len(ids))})", ids
                )
            """,
        )
        == []
    )


def test_placeholder_generator_join_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, ids):
                marks = ",".join("%s" for _ in ids)
                self.env.cr.execute(f"SELECT 1 FROM t WHERE id IN ({marks})", ids)
            """,
        )
        == []
    )


def test_int_cast_interpolation_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, limit):
                self.env.cr.execute(f"SELECT 1 FROM t LIMIT {int(limit)}")
                self.env.cr.execute("SELECT 1 FROM t LIMIT %d" % int(limit))
            """,
        )
        == []
    )


def test_constant_bound_name_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self):
                table = "res_partner"
                self.env.cr.execute(f"SELECT 1 FROM {table}")
            """,
        )
        == []
    )


def test_module_level_constant_is_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            TABLE = "res_partner"
            QUERY = "SELECT 1 FROM " + TABLE


            def run(self):
                self.env.cr.execute(QUERY)
                self.env.cr.execute(f"SELECT 2 FROM {TABLE}")
            """,
        )
        == []
    )


def test_where_fragments_collected_from_constants_are_safe(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, flag, args):
                conds = []
                conds.append("a = %s")
                if flag:
                    conds.append("b = %s")
                self.env.cr.execute("SELECT 1 FROM t WHERE " + " AND ".join(conds), args)
            """,
        )
        == []
    )


def test_parameter_shadows_module_constant(tmp_path: Path):
    diags = _sql(
        tmp_path,
        """\
        table = "res_partner"


        def run(self, table):
            self.env.cr.execute(f"SELECT 1 FROM {table}")
        """,
    )
    assert len(diags) == 1


# --- raw-sql: dynamic construction through containers/branches is reported ----


def test_join_over_list_with_dynamic_fragment_is_flagged(tmp_path: Path):
    diags = _sql(
        tmp_path,
        """\
        def run(self, name):
            parts = ["SELECT 1 FROM t"]
            parts.append(f"WHERE name = '{name}'")
            self.env.cr.execute(" ".join(parts))
        """,
    )
    assert len(diags) == 1


def test_dynamic_fragment_added_via_extend_is_flagged(tmp_path: Path):
    diags = _sql(
        tmp_path,
        """\
        def run(self, names):
            parts = ["SELECT 1 FROM t WHERE"]
            parts.extend([f"name = '{n}'" for n in names])
            self.env.cr.execute(" ".join(parts))
        """,
    )
    assert len(diags) == 1


def test_unsafe_assignment_in_one_branch_is_flagged(tmp_path: Path):
    diags = _sql(
        tmp_path,
        """\
        def run(self, flag, x):
            if flag:
                query = f"SELECT 1 FROM t WHERE x = '{x}'"
            else:
                query = "SELECT 1 FROM t"
            self.env.cr.execute(query)
        """,
    )
    assert len(diags) == 1


def test_both_branches_safe_is_not_flagged(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, flag):
                if flag:
                    query = "SELECT 1 FROM t"
                else:
                    query = "SELECT 2 FROM t"
                self.env.cr.execute(query)
            """,
        )
        == []
    )


def test_unsafe_then_safe_reassignment_in_same_branch_is_not_flagged(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, x):
                query = f"SELECT 1 FROM t WHERE x = '{x}'"
                query = "SELECT 2 FROM t"
                self.env.cr.execute(query)
            """,
        )
        == []
    )


def test_opaque_query_parameter_is_not_flagged(tmp_path: Path):
    assert (
        _sql(
            tmp_path,
            """\
            def run(self, query, args):
                self.env.cr.execute(query, args)
            """,
        )
        == []
    )


def test_interpolating_a_parameter_is_still_flagged(tmp_path: Path):
    diags = _sql(
        tmp_path,
        """\
        def run(self, name):
            self.env.cr.execute(f"SELECT 1 FROM t WHERE name = '{name}'")
        """,
    )
    assert len(diags) == 1


# --- eval-usage ---------------------------------------------------------------


def test_eval_of_constant_bound_name_is_not_flagged(tmp_path: Path):
    assert (
        _eval(
            tmp_path,
            """\
            def run():
                expr = "1 + " + "2"
                return eval(expr)
            """,
        )
        == []
    )


def test_eval_of_parameter_is_flagged(tmp_path: Path):
    assert (
        len(
            _eval(
                tmp_path,
                """\
                def run(expr):
                    return eval(expr)
                """,
            )
        )
        == 1
    )


def test_eval_of_interpolated_name_is_flagged(tmp_path: Path):
    assert (
        len(
            _eval(
                tmp_path,
                """\
                def run(y):
                    expr = f"x + {y}"
                    return eval(expr)
                """,
            )
        )
        == 1
    )


def test_eval_in_one_branch_dynamic_is_flagged(tmp_path: Path):
    assert (
        len(
            _eval(
                tmp_path,
                """\
                def run(flag, y):
                    if flag:
                        expr = y
                    else:
                        expr = "1"
                    return eval(expr)
                """,
            )
        )
        == 1
    )


def test_eval_with_no_arguments_is_still_flagged(tmp_path: Path):
    assert len(_eval(tmp_path, "def run():\n    return eval()\n")) == 1
