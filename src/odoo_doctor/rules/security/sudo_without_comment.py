# src/odoo_doctor/rules/security/sudo_without_comment.py
"""Rule: sudo-without-comment [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
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
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()

    diags: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Attribute) and node.func.attr == "sudo"
        ):
            continue
        lineno = node.lineno
        this_line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        prev_line = lines[lineno - 2] if lineno >= 2 else ""
        if _line_has_comment(this_line) or prev_line.strip().startswith("#"):
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
    return diags
