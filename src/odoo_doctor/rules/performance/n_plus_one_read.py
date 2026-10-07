# src/odoo_doctor/rules/performance/n_plus_one_read.py
"""Rule: n-plus-one-read [Performance, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule

# Methods that return the same single record, possibly in another environment.
_KEEPS_SINGLETON = {"sudo", "with_context", "with_company", "with_user", "with_env"}
# Attributes that are read without touching the database.
_NO_QUERY = {"id", "ids", "env", "pool"}


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _has_prefetch(expr: ast.expr) -> bool:
    """``env['x'].with_prefetch(ids).browse(i)``: the prefetch set is given, no N+1."""
    while isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
        if expr.func.attr == "with_prefetch":
            return True
        expr = expr.func.value
    return False


def _single_browse(expr: ast.expr, loop_vars: set[str]) -> ast.Call | None:
    """The ``browse(<one id that depends on the loop>)`` an expression is built on.

    Only ``sudo()``-like methods may sit between it and the read: ``with_prefetch(...)``
    restores the batching and is the remedy, so it ends the search.
    """
    while isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
        if expr.func.attr == "browse":
            if not expr.args or _has_prefetch(expr.func.value):
                return None
            arg = expr.args[0]
            collection = (ast.List, ast.Tuple, ast.Set, ast.ListComp, ast.SetComp)
            if isinstance(arg, collection) or not _names(arg) & loop_vars:
                return None
            return expr
        if expr.func.attr not in _KEEPS_SINGLETON:
            return None
        expr = expr.func.value
    return None


def _loop_body(node: ast.AST) -> list[ast.AST]:
    """What runs on every iteration of a ``for`` or a comprehension (not its iterable)."""
    if isinstance(node, ast.For):
        return list(node.body)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return [node.elt] + [i for g in node.generators for i in g.ifs]
    if isinstance(node, ast.DictComp):
        return [node.key, node.value] + [i for g in node.generators for i in g.ifs]
    return []


def _targets(node: ast.AST) -> set[str]:
    if isinstance(node, ast.For):
        return _names(node.target)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        return {n for g in node.generators for n in _names(g.target)}
    return set()


def _grow_with_derived_names(loop_vars: set[str], body: list[ast.AST]) -> set[str]:
    """Add names assigned from the loop variables (``pid = row[0]``)."""
    grown = set(loop_vars)
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assign) and _names(node.value) & grown:
                for target in node.targets:
                    grown |= _names(target)
    return grown


@rule(
    name="n-plus-one-read",
    category="Performance",
    tier="P1",
    severity="warning",
    default_confidence="low",
    needs_context=False,
    min_version="14.0",
)
def check_n_plus_one_read(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    if is_test_file(file_path, module_name):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    found: dict[tuple[int, int], str] = {}
    for loop in ast.walk(tree):
        body = _loop_body(loop)
        if not body:
            continue
        loop_vars = _grow_with_derived_names(_targets(loop), body)
        if not loop_vars:
            continue
        # Names bound to a browse(<one id>) record in this loop.
        singles: set[str] = set()
        for stmt in body:
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and _single_browse(node.value, loop_vars)
                ):
                    singles.add(node.targets[0].id)
        for stmt in body:
            for node in ast.walk(stmt):
                if not (
                    isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                ):
                    continue
                if node.attr in _NO_QUERY or node.attr.startswith("_"):
                    continue
                call = parents.get(node)
                if isinstance(call, ast.Call) and call.func is node:
                    continue  # a method call (write, unlink, exists, ...), not a read
                base = node.value
                on_single = isinstance(base, ast.Name) and base.id in singles
                if on_single or _single_browse(base, loop_vars):
                    found.setdefault((node.lineno, node.col_offset), node.attr)

    return [
        Diagnostic(
            module=module_name,
            file_path=str(file_path),
            line=line,
            column=column,
            rule="n-plus-one-read",
            category="Performance",
            severity="warning",
            tier="P1",
            source="native",
            confidence="low",
            title="N+1 read: record browsed one id at a time in a loop",
            message=(
                f"'{attr}' is read at line {line} on a record built by "
                "browse(<one id>) on every iteration: each one starts with an "
                "empty prefetch, so it costs a query per iteration."
            ),
            help=(
                "Browse all the ids once before the loop and iterate that "
                "recordset (prefetch then batches the reads), or call "
                "with_prefetch(ids) on the browsed record."
            ),
            odoo_version=odoo_version,
        )
        for (line, column), attr in sorted(found.items())
    ]
