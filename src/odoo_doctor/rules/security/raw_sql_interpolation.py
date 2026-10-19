# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import is_test_file, pylint_disabled_ranges
from odoo_doctor.rules._taint import Taint, TaintVisitor
from odoo_doctor.rules.registry import rule

_CR_METHODS = {"execute", "executemany"}
# `cr`, `env.cr`, `self._cr`, `request.env.cr`, `request.cr`: anything ending in a cursor name.
_CR_NAMES = {"cr", "_cr"}
# DDL and other statements that do not contain SELECT/UPDATE/INSERT/DELETE/CREATE anyway.
_STATEMENT_START = re.compile(
    r"\s*(WITH|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COPY|VACUUM|REINDEX|ANALYZE|EXPLAIN"
    r"|LOCK|SET|CALL|MERGE)\b",
    re.IGNORECASE,
)


def _is_upgrade_script(file_path: Path) -> bool:
    """`migrations/` (up to Odoo 17) and `upgrades/` (Odoo 18+) hold one-off scripts."""
    return bool({"migrations", "upgrades"} & set(Path(file_path).parts))


@rule(
    name="raw-sql-string-interpolation",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_raw_sql_interpolation(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Find cr.execute() calls with dynamically interpolated SQL strings."""
    # Tests and migration/upgrade scripts run on a developer's or admin's database, never on
    # request data, so dynamic SQL there is not an injection vector.
    if is_test_file(file_path, module_name) or _is_upgrade_script(file_path):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    visitor = _RawSqlVisitor(
        file_path,
        module_name,
        odoo_version,
        pylint_disabled_ranges(read_source(file_path) or "", tree, ("sql-injection",))
        + _input_free_hook_ranges(tree),
    )
    visitor.visit(tree)
    return visitor.diagnostics


# ORM hooks that run at install/upgrade time (SQL views are created in `init`).
_INSTALL_HOOKS = {"init", "_auto_init"}


def _input_free_hook_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges of install-time hooks that take nothing but ``self``.

    With no parameter, no caller-supplied data reaches the SQL they build, only class
    metadata such as ``self._table`` and ``self._query()``.
    """
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            takes_only_self = (
                len(args.args) + len(args.posonlyargs) == 1
                and not args.kwonlyargs
                and args.vararg is None
                and args.kwarg is None
            )
            if node.name in _INSTALL_HOOKS and takes_only_self:
                ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


class _RawSqlVisitor(TaintVisitor):
    def __init__(
        self,
        file_path: Path,
        module_name: str,
        odoo_version: str,
        disabled_ranges: list[tuple[int, int]] | None = None,
    ) -> None:
        super().__init__()
        self._disabled_ranges = disabled_ranges or []
        self.file_path = file_path
        self.module_name = module_name
        self.odoo_version = odoo_version
        self.diagnostics: list[Diagnostic] = []
        # shortcut: cursor names are file-wide, not scoped; a reused name only widens matching.
        self._cursors: set[str] = set()

    def _note_cursor(self, target: ast.expr | None, value: ast.expr) -> None:
        if isinstance(target, ast.Name) and _opens_cursor(value):
            self._cursors.add(target.id)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._note_cursor(target, node.value)
        super().visit_Assign(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self._note_cursor(item.optional_vars, item.context_expr)
        super().visit_With(node)

    def check_call(self, node: ast.Call) -> None:
        if not (_is_cursor_execute(node, self._cursors) and node.args):
            return
        sql_arg = node.args[0]
        if _is_plain_text_format(sql_arg):
            return
        if self.taint(sql_arg) != Taint.UNSAFE:
            return
        if any(start <= node.lineno <= end for start, end in self._disabled_ranges):
            return
        self.diagnostics.append(
            _make_diagnostic(node, self.file_path, self.module_name, self.odoo_version)
        )


def _opens_cursor(node: ast.expr) -> bool:
    """`registry.cursor()`, `self.pool.cursor()`, `closing(registry.cursor())`."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cursor":
            return True
        return any(_opens_cursor(a) for a in node.args)
    return False


def _is_cursor_execute(node: ast.Call, cursors: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _CR_METHODS:
        return False
    receiver = node.func.value
    if _opens_cursor(receiver):
        return True
    name = _dotted_name(receiver)
    return name.rsplit(".", 1)[-1] in _CR_NAMES or name in cursors


def _is_plain_text_format(node: ast.expr) -> bool:
    """`"some {} text".format(x)` with no SQL keyword is not a query being built."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    receiver = node.func.value
    return (
        node.func.attr == "format"
        and isinstance(receiver, ast.Constant)
        and isinstance(receiver.value, str)
        and not any(
            token in receiver.value.upper()
            for token in ("SELECT", "UPDATE", "INSERT", "DELETE", "CREATE")
        )
        and not _STATEMENT_START.match(receiver.value)
    )


def _dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _make_diagnostic(
    node: ast.Call, file_path: Path, module_name: str, odoo_version: str
) -> Diagnostic:
    method = node.func.attr if isinstance(node.func, ast.Attribute) else "execute"
    return Diagnostic(
        module=module_name,
        file_path=str(file_path),
        line=node.lineno,
        column=node.col_offset,
        rule="raw-sql-string-interpolation",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="SQL injection via string interpolation",
        message=f"'{method}()' at line {node.lineno} uses dynamic SQL string construction. Vulnerable to SQL injection.",
        help="Use parameterized queries: cr.execute('SELECT ... WHERE name = %s', (param,)).",
        odoo_version=odoo_version,
    )
