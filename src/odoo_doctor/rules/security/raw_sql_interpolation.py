# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
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
    tree = parse_python(file_path)
    if tree is None:
        return []

    visitor = _RawSqlVisitor(
        file_path,
        module_name,
        odoo_version,
        _pylint_disabled_ranges(read_source(file_path) or "", tree),
    )
    visitor.visit(tree)
    return visitor.diagnostics


# pylint-odoo's own check for this pattern. A developer who writes this marker is
# explicitly asserting the dynamic part is not user data (e.g. a WHERE fragment
# whose values are bound through parameters), so we honour it like pylint does.
_PYLINT_DISABLE_RE = re.compile(r"pylint:\s*disable\s*=\s*([\w\-,\s]+)")


def _pylint_disabled_ranges(source: str, tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges where `# pylint: disable=sql-injection` is in effect.

    A trailing comment covers its own line; a comment on its own line covers the
    rest of the enclosing function (or module), as in pylint.
    """
    scopes = [
        (n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    ranges: list[tuple[int, int]] = []
    if "pylint" not in source:  # tokenizing every file only to find nothing is slow
        return ranges
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return ranges
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _PYLINT_DISABLE_RE.search(tok.string)
        if not match or "sql-injection" not in {
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
