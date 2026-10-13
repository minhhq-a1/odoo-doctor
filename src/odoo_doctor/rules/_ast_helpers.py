# src/odoo_doctor/rules/_ast_helpers.py
"""Shared AST helper functions for rules."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import deque
from collections.abc import Iterable, Iterator
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


def _path_below_addon(file_path: Path | str, module_name: str) -> tuple[str, ...]:
    """Path components below the addon directory (the last two if it is not on the path)."""
    parts = Path(file_path).parts
    if module_name in parts:
        return parts[len(parts) - parts[::-1].index(module_name) :]
    return parts[-2:]


def is_test_file(file_path: Path | str, module_name: str) -> bool:
    """True if the file sits in a `tests/` directory *inside* the addon.

    Only path components below the addon directory count, so an addon that lives
    under some unrelated `tests/` folder is not mistaken for test code.
    """
    return "tests" in _path_below_addon(file_path, module_name)[:-1]


def is_migration_file(file_path: Path | str, module_name: str) -> bool:
    """True for a script in the addon's `migrations/` directory.

    Those scripts run against databases of the version being left, so APIs removed in
    the new version are legitimate there.
    """
    return "migrations" in _path_below_addon(file_path, module_name)[:-1]


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


_MODEL_BASE_NAMES = {"Model", "TransientModel", "AbstractModel", "BaseModel"}


def is_model_class(cls: ast.ClassDef) -> bool:
    """True for a class that declares an Odoo model.

    It either derives from ``models.Model`` / ``TransientModel`` / ``AbstractModel`` /
    ``BaseModel`` or sets ``_name`` / ``_inherit`` itself. A plain Python mixin without
    either is not a model, even though models may inherit from it.
    """
    for base in cls.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name in _MODEL_BASE_NAMES:
            return True
    for stmt in cls.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else []
        if isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        if any(
            isinstance(t, ast.Name) and t.id in ("_name", "_inherit") for t in targets
        ):
            return True
    return False


def odoo_major(version: str) -> int | None:
    """Major number of an Odoo version string (``"19.0"`` -> 19), None if unparsable."""
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


_RECORD_ROOTS = {"self", "cls", "env", "request"}


def receiver_kind(node: ast.expr) -> str:
    """``record`` (self / env / request rooted), ``super`` or ``other`` for a call receiver."""
    while True:
        if isinstance(node, ast.Attribute):
            if node.attr == "env":
                return "record"
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "super":
                return "super"
            node = node.func
        else:
            break
    if isinstance(node, ast.Name) and node.id in _RECORD_ROOTS:
        return "record"
    return "other"


# pylint-odoo's own marker. A developer who writes it is explicitly asserting that the
# flagged pattern is intended, so rules covering the same check honour it like pylint.
_PYLINT_DISABLE_RE = re.compile(r"pylint:\s*disable\s*=\s*([\w\-,\s]+)")


def pylint_disabled_ranges(
    source: str, tree: ast.AST, names: Iterable[str]
) -> list[tuple[int, int]]:
    """Line ranges where ``# pylint: disable=<one of names>`` is in effect.

    A trailing comment covers its own line; a comment on its own line covers the
    rest of the enclosing function (or module), as in pylint.
    """
    wanted = set(names)
    ranges: list[tuple[int, int]] = []
    if "pylint" not in source:  # tokenizing every file only to find nothing is slow
        return ranges
    scopes = [
        (n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return ranges
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _PYLINT_DISABLE_RE.search(tok.string)
        if not match or not wanted & {
            name.strip() for name in match.group(1).split(",")
        }:
            continue
        line = tok.start[0]
        if tok.line[: tok.start[1]].strip():  # trailing comment
            ranges.append((line, line))
            continue
        enclosing = [end for start, end in scopes if start <= line <= end]
        ranges.append((line, min(enclosing) if enclosing else 10**9))
    return ranges
