# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

_CR_METHODS = {"execute", "executemany"}
_CR_OBJECTS = {"cr", "env.cr", "_cr", "self.env.cr", "self._cr", "cls.env.cr", "cls._cr"}


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
    try:
        tree = ast.parse(file_path.read_text())
    except (SyntaxError, OSError):
        return []

    visitor = _RawSqlVisitor(file_path, module_name, odoo_version)
    visitor.visit(tree)
    return visitor.diagnostics


class _RawSqlVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, module_name: str, odoo_version: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.odoo_version = odoo_version
        self.diagnostics: list[Diagnostic] = []
        self._unsafe_stack: list[set[str]] = [set()]

    @property
    def _unsafe_names(self) -> set[str]:
        return self._unsafe_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._unsafe_stack.append(set())
        self.generic_visit(node)
        self._unsafe_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:
        is_unsafe = _is_unsafe_sql_expr(node.value, self._unsafe_names)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if is_unsafe:
                    self._unsafe_names.add(target.id)
                else:
                    self._unsafe_names.discard(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            if _is_unsafe_sql_expr(node.value, self._unsafe_names):
                self._unsafe_names.add(node.target.id)
            else:
                self._unsafe_names.discard(node.target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name) and isinstance(node.op, ast.Add):
            if node.target.id in self._unsafe_names or _is_dynamic_expr(node.value, self._unsafe_names):
                self._unsafe_names.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_cursor_execute(node) and node.args:
            sql_arg = node.args[0]
            if _is_unsafe_sql_expr(sql_arg, self._unsafe_names):
                self.diagnostics.append(_make_diagnostic(
                    node, self.file_path, self.module_name, self.odoo_version
                ))
        self.generic_visit(node)


def _is_cursor_execute(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _CR_METHODS:
        return False
    return _dotted_name(node.func.value) in _CR_OBJECTS


def _is_unsafe_sql_expr(node: ast.expr, unsafe_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in unsafe_names
    if isinstance(node, ast.JoinedStr):
        return not _is_safe_fstring(node)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            return True
        if isinstance(node.op, ast.Add):
            return _is_dynamic_expr(node.left, unsafe_names) or _is_dynamic_expr(node.right, unsafe_names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format" and _looks_like_sql(node.func.value):
            return True
    return False


def _is_dynamic_expr(node: ast.expr, unsafe_names: set[str]) -> bool:
    if _is_unsafe_sql_expr(node, unsafe_names):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return False
    if _is_safe_table_name(node):
        return False
    return True


def _looks_like_sql(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(token in node.value.upper() for token in ("SELECT", "UPDATE", "INSERT", "DELETE", "CREATE"))
    return True


def _is_safe_fstring(node: ast.JoinedStr) -> bool:
    """Allow view/table DDL f-strings that only interpolate self._table or cls._table."""
    for val in node.values:
        if isinstance(val, ast.FormattedValue) and not _is_safe_table_name(val.value):
            return False
    return True


def _is_safe_table_name(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"self", "cls"}
        and node.attr == "_table"
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
