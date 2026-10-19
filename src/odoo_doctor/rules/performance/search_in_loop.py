# src/odoo_doctor/rules/performance/search_in_loop.py
"""Rule: search-in-loop [Performance, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file, orm_calls_in_loops
from odoo_doctor.rules.registry import rule

# browse() only wraps ids in a recordset; it does not hit the database.
_ORM_METHODS = {
    "search",
    "search_count",
    "read",
    "search_read",
    "search_fetch",
    "read_group",
    "_read_group",
}


@rule(
    name="search-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_search_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    if is_test_file(file_path, module_name):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    for node, loop in orm_calls_in_loops(tree, _ORM_METHODS):
        if isinstance(loop, ast.While) and _is_paged(node):
            continue
        method = node.func.attr
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="search-in-loop",
                category="Performance",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"ORM '{method}' called inside loop",
                message=f"'{method}()' at line {node.lineno} is called inside a loop. Consider batching.",
                help=f"Move the '{method}()' call outside the loop and batch the operation.",
                odoo_version=odoo_version,
            )
        )
    return diags


def _is_paged(call: ast.Call) -> bool:
    """``search(..., limit=N)`` with a batch size: the paging that a ``while`` loop over
    chunks is made of. ``limit=1`` is a plain lookup per iteration and still counts."""
    for kw in call.keywords:
        if kw.arg == "limit":
            return not (isinstance(kw.value, ast.Constant) and kw.value.value in (0, 1))
    return False
