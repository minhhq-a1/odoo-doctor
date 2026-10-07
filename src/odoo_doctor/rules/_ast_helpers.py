# src/odoo_doctor/rules/_ast_helpers.py
"""Shared AST helper functions for rules."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterator
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


def per_iteration_nodes(loop: ast.For | ast.While) -> Iterator[ast.AST]:
    """Nodes that run on every iteration of *loop*.

    That is its body (and, for a ``while``, its condition). The iterable of a ``for`` and
    its ``else`` clause run once, so they are not in the loop. A nested loop is the
    business of its own check, except that its iterable and ``else`` clause run once per
    iteration of this one and are yielded here.
    """
    todo: deque[ast.AST] = deque(loop.body)
    if isinstance(loop, ast.While):
        todo.appendleft(loop.test)
    while todo:
        curr = todo.popleft()
        yield curr
        if isinstance(curr, (ast.For, ast.While)):
            if isinstance(curr, ast.For):
                todo.append(curr.iter)
            todo.extend(curr.orelse)
        else:
            todo.extend(ast.iter_child_nodes(curr))


def is_bounded_loop(loop: ast.For | ast.While) -> bool:
    """A ``for`` whose iteration count does not scale with the data.

    Loops over chunks (``split_every(...)``, ``range(start, stop, step)``) run once per
    chunk, which is the remedy for a per-record call, and a loop over a literal tuple /
    list of constants is bounded by the source code.
    """
    if not isinstance(loop, ast.For):
        return False
    it = loop.iter
    if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
        return all(isinstance(e, ast.Constant) for e in it.elts)
    if isinstance(it, ast.Call):
        name = (
            it.func.id
            if isinstance(it.func, ast.Name)
            else it.func.attr
            if isinstance(it.func, ast.Attribute)
            else None
        )
        if name == "split_every":
            return True
        if name == "range" and len(it.args) == 3:
            return True
    return False
