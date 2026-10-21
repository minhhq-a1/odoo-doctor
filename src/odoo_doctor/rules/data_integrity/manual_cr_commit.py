# src/odoo_doctor/rules/data_integrity/manual_cr_commit.py
"""Rule: manual-cr-commit [Data Integrity, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import (
    is_migration_file,
    is_test_file,
    pylint_disabled_ranges,
)
from odoo_doctor.rules.registry import rule

# pylint-odoo's name for this check (E8102).
_PYLINT_NAMES = ("invalid-commit", "E8102")

# Code that runs at install time or under its own transaction handling.
_HOOK_FUNCTIONS = {
    "init",
    "_auto_init",
    "post_init_hook",
    "pre_init_hook",
    "uninstall_hook",
    "post_load",
}

# A commit under `if auto_commit:` / `if self._can_commit():` / `if ctx.get("commit_x")` or
# `if not tools.config["test_enable"]:` is a caller's opt-in (Odoo core batches this way).
_OPT_IN_GUARDS = ("commit", "test_enable", "testing", "current_test", "in_test_mode")


def _chain(node: ast.expr) -> list[str]:
    """Attribute names from the root down: ``self.env.cr`` -> ``["self", "env", "cr"]``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return parts[::-1]


def _creates_own_cursor(node: ast.expr | None) -> bool:
    """``registry.cursor()``, ``self.pool.cursor()``, ``api.Environment(cr, ...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in ("cursor", "Environment")


def _own_names(scope: ast.AST) -> set[str]:
    """Names bound to a cursor or environment *scope* opened itself, not its nested functions."""
    own: set[str] = set()
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.Assign) and _creates_own_cursor(node.value):
            own.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if _creates_own_cursor(item.context_expr) and isinstance(
                    item.optional_vars, ast.Name
                ):
                    own.add(item.optional_vars.id)
        todo.extend(ast.iter_child_nodes(node))
    return own


def _parameter_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    names += [a.arg for a in (args.vararg, args.kwarg) if a]
    return set(names)


# Methods Odoo itself calls in the middle of a write, a computation or a check. A commit
# there splits an operation the caller expects to be atomic.
_ORM_HOOKS = {
    "create",
    "write",
    "unlink",
    "copy",
    "default_get",
    "name_search",
    "_search",
    "_name_search",
    "_read",
    "read",
}
_ORM_HOOK_PREFIXES = ("_compute_", "_inverse_")
_ORM_HOOK_DECORATORS = {"constrains", "onchange", "depends"}


def _is_orm_hook(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if func.name in _ORM_HOOKS or func.name.startswith(_ORM_HOOK_PREFIXES):
        return True
    for decorator in func.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else ""
        if name in _ORM_HOOK_DECORATORS:
            return True
    return False


class _Finder(ast.NodeVisitor):
    def __init__(self, module_own: set[str]) -> None:
        # (cursors opened, parameters) of the module body, then of each enclosing function.
        self._own: list[tuple[set[str], set[str]]] = [(module_own, set())]
        self.found: list[tuple[ast.Call, str]] = []
        self._functions: list[str] = []
        self._hooks: list[bool] = []
        self._guarded = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._functions.append(node.name)
        self._hooks.append(_is_orm_hook(node))
        self._own.append((_own_names(node), _parameter_names(node)))
        self.generic_visit(node)
        self._own.pop()
        self._hooks.pop()
        self._functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_If(self, node: ast.If) -> None:
        test = ast.unparse(node.test).lower()
        guarded = any(token in test for token in _OPT_IN_GUARDS)
        self._guarded += guarded
        self.generic_visit(node)
        self._guarded -= guarded

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "commit"):
            return
        chain = _chain(func.value)
        if not chain or chain[-1] not in ("cr", "_cr"):
            return
        if self._guarded or self._exempt_function():
            return
        if self._is_own(chain[0]):
            return  # a cursor this code opened: committing it is its job
        in_hook = chain[0] in ("self", "cls") and any(self._hooks)
        self.found.append((node, "hook" if in_hook else "other"))

    def _is_own(self, name: str) -> bool:
        """The nearest scope that binds *name* opened it (a parameter shadows an outer one)."""
        for own, params in reversed(self._own):
            if name in own:
                return True
            if name in params:
                return False
        return False

    def _exempt_function(self) -> bool:
        return any(
            name in _HOOK_FUNCTIONS or "cron" in name.lower()
            for name in self._functions
        )


@rule(
    name="manual-cr-commit",
    category="Data Integrity",
    tier="P1",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_manual_cr_commit(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag ``cr.commit()`` on the transaction Odoo opened for the current request."""
    if is_test_file(file_path, module_name) or is_migration_file(
        file_path, module_name
    ):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []
    finder = _Finder(_own_names(tree))
    finder.visit(tree)
    if not finder.found:
        return []
    disabled = pylint_disabled_ranges(read_source(file_path) or "", tree, _PYLINT_NAMES)

    diags: list[Diagnostic] = []
    for node, kind in finder.found:
        if any(start <= node.lineno <= end for start, end in disabled):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="manual-cr-commit",
                category="Data Integrity",
                severity="warning",
                tier="P1",
                source="native",
                confidence="high" if kind == "hook" else "medium",
                title="Manual commit of the request transaction",
                message=(
                    "`cr.commit()` ends the transaction Odoo opened for this request. Work "
                    "done before it can no longer be rolled back, so a later error leaves "
                    "the database half updated, and the ORM cache and pending "
                    "computations are not flushed in a defined order."
                ),
                help=(
                    "Remove the commit and let Odoo commit when the request succeeds. "
                    "For batch work, run it from a cron or a queue job, or do it in "
                    "its own cursor (`with self.pool.cursor() as cr:`). "
                    "`# pylint: disable=invalid-commit` marks an intended one."
                ),
                odoo_version=odoo_version,
            )
        )
    return diags
