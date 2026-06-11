# src/odoo_doctor/rules/correctness/missing_translation.py
"""Rule: missing-translation [Maintainability, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules.registry import rule

_USER_FACING = {"UserError", "ValidationError", "Warning", "RedirectWarning"}


def _func_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_bare_string_arg(call: ast.Call) -> bool:
    if not call.args:
        return False
    first = call.args[0]
    # Flag only when the message is a literal string (or an f-string /
    # concatenation of literals) and NOT a _() call.
    if isinstance(first, ast.Call) and _func_name(first.func) == "_":
        return False
    return isinstance(first, (ast.Constant, ast.JoinedStr)) and (
        isinstance(first, ast.JoinedStr) or isinstance(first.value, str)
    )


@rule(
    name="missing-translation",
    category="Maintainability",
    tier="P2",
    severity="info",
    default_confidence="medium",
    needs_context=False,
    min_version="14.0",
)
def check_missing_translation(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    diags: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node.func)
        if name not in _USER_FACING:
            continue
        if not _is_bare_string_arg(node):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="missing-translation",
                category="Maintainability",
                severity="info",
                tier="P2",
                source="native",
                confidence="medium",
                title=f"Untranslated message in {name}(...)",
                message=(
                    f"The message passed to {name}(...) is not wrapped in _(), "
                    "so it will not be translated."
                ),
                help='Wrap the message in _(), e.g. raise UserError(_("...")).',
                odoo_version=odoo_version,
            )
        )
    return diags
