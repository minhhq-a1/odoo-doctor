# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import is_test_file, pylint_disabled_ranges
from odoo_doctor.rules._taint import Taint, TaintVisitor
from odoo_doctor.rules.registry import rule

_CR_METHODS = {"execute", "executemany"}
_CR_OBJECTS = {
    "cr",
    "env.cr",
    "_cr",
    "self.env.cr",
    "self._cr",
    "cls.env.cr",
    "cls._cr",
}


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

    def check_call(self, node: ast.Call) -> None:
        if not (_is_cursor_execute(node) and node.args):
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


def _is_cursor_execute(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _CR_METHODS:
        return False
    return _dotted_name(node.func.value) in _CR_OBJECTS


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
