# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

_CR_METHODS = {"execute", "executemany"}
_CR_OBJECTS = {"cr", "env.cr", "_cr", "self.env.cr", "self._cr"}


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
    """Find cr.execute() calls with f-string or %-formatted SQL."""
    diags: list[Diagnostic] = []

    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _CR_METHODS:
            continue

        # Check if the receiver looks like a cursor (cr or env.cr)
        receiver = node.func.value
        receiver_str = _dotted_name(receiver)
        if receiver_str not in _CR_OBJECTS:
            continue

        # First argument is the SQL string — check if it's an f-string or %-formatted
        if not node.args:
            continue

        sql_arg = node.args[0]

        is_unsafe = False
        if _is_fstring(sql_arg):
            is_unsafe = not _is_safe_fstring(sql_arg)
        elif _is_percent_format(sql_arg):
            is_unsafe = True

        if is_unsafe:
            diags.append(Diagnostic(
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
                message=f"'{node.func.attr}()' at line {node.lineno} uses string interpolation in SQL. Vulnerable to SQL injection.",
                help="Use parameterized queries: cr.execute('SELECT ...', (param,)) instead of f-strings or %.",
                odoo_version=odoo_version,
            ))

    return diags


def _is_fstring(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr)


def _is_safe_fstring(node: ast.JoinedStr) -> bool:
    """Check if the f-string only interpolates self._table or cls._table."""
    for val in node.values:
        if isinstance(val, ast.FormattedValue):
            expr = val.value
            if not isinstance(expr, ast.Attribute):
                return False
            if not isinstance(expr.value, ast.Name):
                return False
            if expr.value.id not in {"self", "cls"}:
                return False
            if expr.attr != "_table":
                return False
    return True


def _is_percent_format(node: ast.expr) -> bool:
    """Check if the node is a %-formatted string like 'SELECT ... %s' % value."""
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)


def _dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
