# src/odoo_doctor/rules/performance/search_in_loop.py
"""Rule: search-in-loop [Performance, P1]."""

from __future__ import annotations

import ast
from collections.abc import Generator
from pathlib import Path

from odoo_doctor.core.source import read_source
from odoo_doctor.rules._ast_helpers import receiver_is_orm

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

_ORM_METHODS = {"search", "search_count", "browse", "read"}


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

    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    _walk_for_loops(tree, diags, file_path, module_name, odoo_version)
    return diags


def _walk_for_loops(
    node: ast.AST,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
    orm_vars: set[str] | None = None,
) -> None:
    """Recursively find ORM calls inside for/while loops."""
    orm_vars = set(orm_vars) if orm_vars else set()

    if isinstance(node, ast.For):
        from odoo_doctor.rules._ast_helpers import node_is_orm

        if node_is_orm(node.iter, orm_vars):
            if isinstance(node.target, ast.Name):
                orm_vars.add(node.target.id)
            elif isinstance(node.target, ast.Tuple):
                for el in node.target.elts:
                    if isinstance(el, ast.Name):
                        orm_vars.add(el.id)

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            _check_loop_body(child, diags, file_path, module, version, orm_vars)
        _walk_for_loops(child, diags, file_path, module, version, orm_vars)


def _walk_excluding_nested_loops(node: ast.AST) -> Generator[ast.AST, None, None]:
    from collections import deque

    todo = deque(ast.iter_child_nodes(node))
    while todo:
        curr = todo.popleft()
        yield curr
        if not isinstance(curr, (ast.For, ast.While)):
            todo.extend(ast.iter_child_nodes(curr))


def _check_loop_body(
    loop: ast.For | ast.While,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
    orm_vars: set[str],
) -> None:
    """Check if any ORM method call exists inside a loop body."""
    local_orm_vars = set(orm_vars)
    if isinstance(loop, ast.For):
        from odoo_doctor.rules._ast_helpers import node_is_orm

        if node_is_orm(loop.iter, local_orm_vars):
            if isinstance(loop.target, ast.Name):
                local_orm_vars.add(loop.target.id)
            elif isinstance(loop.target, ast.Tuple):
                for el in loop.target.elts:
                    if isinstance(el, ast.Name):
                        local_orm_vars.add(el.id)

    for node in _walk_excluding_nested_loops(loop):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in _ORM_METHODS:
            if not receiver_is_orm(node, local_orm_vars):
                continue
            diags.append(
                Diagnostic(
                    module=module,
                    file_path=str(file_path),
                    line=node.lineno,
                    column=node.col_offset,
                    rule="search-in-loop",
                    category="Performance",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"ORM '{node.func.attr}' called inside loop",
                    message=f"'{node.func.attr}()' at line {node.lineno} is called inside a loop. Consider batching.",
                    help=f"Move the '{node.func.attr}()' call outside the loop and batch the operation.",
                    odoo_version=version,
                )
            )
