# src/odoo_doctor/rules/performance/create_write_in_loop.py
"""Rules: create-in-loop, write-in-loop [Performance, P1]."""

from __future__ import annotations

import ast
from collections.abc import Generator
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules._ast_helpers import receiver_is_orm
from odoo_doctor.rules.registry import rule


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
    method_name: str,
    rule_name: str,
) -> None:
    for node in _walk_excluding_nested_loops(loop):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == method_name:
            if not receiver_is_orm(node):
                continue
            diags.append(
                Diagnostic(
                    module=module,
                    file_path=str(file_path),
                    line=node.lineno,
                    column=node.col_offset,
                    rule=rule_name,
                    category="Performance",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"ORM '{method_name}' called inside loop",
                    message=f"'{method_name}()' at line {node.lineno} is called inside a loop. Consider batching.",
                    help=f"Move the '{method_name}()' call outside the loop and batch the operation.",
                    odoo_version=version,
                )
            )


def _walk_for_loops(
    node: ast.AST,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
    method_name: str,
    rule_name: str,
) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            _check_loop_body(child, diags, file_path, module, version, method_name, rule_name)
        _walk_for_loops(child, diags, file_path, module, version, method_name, rule_name)


def check_create_write_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Helper used by tests to get both."""
    return check_create_in_loop(file_path, module_name, odoo_version) + check_write_in_loop(file_path, module_name, odoo_version)


@rule(
    name="create-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_create_in_loop(
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
    _walk_for_loops(tree, diags, file_path, module_name, odoo_version, "create", "create-in-loop")
    return diags


@rule(
    name="write-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_write_in_loop(
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
    _walk_for_loops(tree, diags, file_path, module_name, odoo_version, "write", "write-in-loop")
    return diags
