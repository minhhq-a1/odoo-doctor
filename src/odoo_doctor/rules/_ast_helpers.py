# src/odoo_doctor/rules/_ast_helpers.py
"""Shared AST helper functions for rules."""

from __future__ import annotations

import ast
from pathlib import Path


def node_is_orm(node: ast.AST, orm_vars: set[str] | None = None) -> bool:
    """Check if an AST node evaluates to an ORM object."""
    has_env_subscript = [False]
    root_name = [None]

    def check_node(n: ast.AST) -> None:
        if isinstance(n, ast.Name):
            root_name[0] = n.id
        elif isinstance(n, ast.Attribute):
            check_node(n.value)
        elif isinstance(n, ast.Subscript):
            sub_val = n.value
            is_env = False
            if (
                isinstance(sub_val, ast.Name)
                and sub_val.id == "env"
                or isinstance(sub_val, ast.Attribute)
                and sub_val.attr == "env"
            ):
                is_env = True
            if is_env:
                has_env_subscript[0] = True
            check_node(sub_val)
        elif isinstance(n, ast.Call):
            check_node(n.func)

    check_node(node)

    if root_name[0] in ("self", "cls"):
        return True
    if has_env_subscript[0]:
        return True
    if orm_vars and root_name[0] in orm_vars:
        return True

    return False


def receiver_is_orm(call: ast.Call, orm_vars: set[str] | None = None) -> bool:
    """Check if the receiver of a method call is likely an ORM object."""
    if not isinstance(call.func, ast.Attribute):
        return False
    return node_is_orm(call.func.value, orm_vars)


def is_test_file(file_path: Path | str, module_name: str) -> bool:
    """True if the file sits in a `tests/` directory *inside* the addon.

    Only path components below the addon directory count, so an addon that lives
    under some unrelated `tests/` folder is not mistaken for test code.
    """
    parts = Path(file_path).parts
    if module_name in parts:
        rel = parts[len(parts) - parts[::-1].index(module_name) :]
    else:
        rel = parts[-2:]
    return "tests" in rel[:-1]
