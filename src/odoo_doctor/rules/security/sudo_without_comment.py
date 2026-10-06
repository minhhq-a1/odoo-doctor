# src/odoo_doctor/rules/security/sudo_without_comment.py
"""Rule: sudo-without-comment [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule


def _line_has_comment(line: str) -> bool:
    # Strip strings crudely; good enough for a heuristic comment check.
    in_str = None
    for i, ch in enumerate(line):
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
        elif ch == "#":
            return True
    return False


def _calls_with_statement(tree: ast.AST):
    """Yield every ``ast.Call`` with the innermost statement that contains it."""
    stack: list[tuple[ast.AST, ast.stmt | None]] = [(tree, None)]
    while stack:
        node, stmt = stack.pop()
        if isinstance(node, ast.stmt):
            stmt = node
        if isinstance(node, ast.Call):
            yield node, stmt
        stack.extend((child, stmt) for child in ast.iter_child_nodes(node))


def _drops_privileges(call: ast.Call) -> bool:
    """``.sudo(False)`` returns the non-superuser environment: nothing to justify."""
    values = [*call.args[:1], *(k.value for k in call.keywords)]
    return any(isinstance(v, ast.Constant) and v.value is False for v in values)


def _statement_span(stmt: ast.stmt) -> tuple[int, int]:
    """Lines of the statement itself; for a compound one, its header only (a comment in
    the body says nothing about a ``sudo()`` in the ``if`` / ``for`` / ``with`` line)."""
    nested = (ast.stmt, ast.ExceptHandler, ast.match_case)
    children = list(ast.iter_child_nodes(stmt))
    if not any(isinstance(c, nested) for c in children):
        return stmt.lineno, stmt.end_lineno or stmt.lineno
    end = stmt.lineno
    for child in children:
        if isinstance(child, nested):
            continue
        for n in ast.walk(child):
            end = max(end, getattr(n, "end_lineno", None) or 0)
    return stmt.lineno, end


def _is_justified(lines: list[str], span: tuple[int, int], sudo_line: int) -> bool:
    """A comment on any line of the statement, or on the line right above its start or
    above the ``.sudo()`` line (a chain can put ``.sudo()`` several lines down)."""
    first, last = span
    for lineno in range(first, last + 1):
        if 0 < lineno <= len(lines) and _line_has_comment(lines[lineno - 1]):
            return True
    for lineno in {first, sudo_line}:
        if lineno >= 2 and lines[lineno - 2].strip().startswith("#"):
            return True
    return False


@rule(
    name="sudo-without-comment",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="medium",
    needs_context=False,
    min_version="14.0",
)
def check_sudo_without_comment(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    if is_test_file(file_path, module_name) or "migrations" in Path(file_path).parts:
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    lines = (read_source(file_path) or "").splitlines()

    diags: list[Diagnostic] = []
    for node, stmt in _calls_with_statement(tree):
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "sudo"):
            continue
        if _drops_privileges(node):
            continue
        lineno = node.lineno
        span = _statement_span(stmt) if stmt is not None else (lineno, lineno)
        if _is_justified(lines, span, node.func.end_lineno or lineno):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=lineno,
                column=node.col_offset,
                rule="sudo-without-comment",
                category="Security",
                severity="warning",
                tier="P1",
                source="native",
                confidence="medium",
                title="'.sudo()' without a justifying comment",
                message=(
                    f".sudo() at line {lineno} bypasses access rights but has "
                    "no comment explaining why it is safe."
                ),
                help=(
                    "Add a short comment on the same line or directly above "
                    "explaining why elevated privileges are required."
                ),
                odoo_version=odoo_version,
            )
        )
    return sorted(diags, key=lambda d: (d.line, d.column))
