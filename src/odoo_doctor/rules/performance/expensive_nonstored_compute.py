# src/odoo_doctor/rules/performance/expensive_nonstored_compute.py
"""Rule: expensive-nonstored-compute [Performance, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import receiver_is_orm
from odoo_doctor.rules.registry import rule

_QUERY_METHODS = {
    "search",
    "search_count",
    "search_read",
    "read_group",
    "_read_group",
}


def _field_call(value: ast.expr) -> ast.Call | None:
    """Return the call node when *value* is ``fields.<Type>(...)``."""
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "fields"
    ):
        return value
    return None


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _first_query(func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    queries = [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in _QUERY_METHODS
        and receiver_is_orm(n)
    ]
    return min(queries, key=lambda n: (n.lineno, n.col_offset), default=None)


@rule(
    name="expensive-nonstored-compute",
    category="Performance",
    tier="P2",
    severity="warning",
    default_confidence="medium",
    needs_context=False,
    min_version="14.0",
)
def check_expensive_nonstored_compute(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        methods = {
            n.name: n
            for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for stmt in cls.body:
            if not (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                continue
            call = _field_call(stmt.value)
            if call is None:
                continue
            compute = _kwarg(call, "compute")
            if not (
                isinstance(compute, ast.Constant) and isinstance(compute.value, str)
            ):
                continue
            if _is_true(_kwarg(call, "store")):
                continue
            func = methods.get(compute.value)
            if func is None:
                continue
            query = _first_query(func)
            if query is None:
                continue
            field_name = stmt.targets[0].id
            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=str(file_path),
                    line=stmt.lineno,
                    column=stmt.col_offset,
                    rule="expensive-nonstored-compute",
                    category="Performance",
                    severity="warning",
                    tier="P2",
                    source="native",
                    confidence="medium",
                    title=f"Non-stored computed field '{field_name}' runs a query",
                    message=(
                        f"'{field_name}' is not stored, so '{compute.value}' "
                        f"(which calls {query.func.attr}() on line "
                        f"{query.lineno}) runs every time the field is read, "
                        "including list views and exports."
                    ),
                    help=(
                        "Add store=True with a complete @api.depends, or move the "
                        "aggregate into a stored field / read_group at the call "
                        "site."
                    ),
                    odoo_version=odoo_version,
                )
            )
    return diags
