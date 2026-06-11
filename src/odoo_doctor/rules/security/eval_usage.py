# src/odoo_doctor/rules/security/eval_usage.py
"""Rule: eval-usage [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules.registry import rule

_DANGEROUS = {"eval", "exec"}


@rule(
    name="eval-usage",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_eval_usage(
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
        # Only the bare builtin names eval / exec (not attribute calls like
        # tools.safe_eval, which is a separate, sandboxed function).
        if not (isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS):
            continue
        # A literal-only argument (eval("1+1")) is far less risky; flag when the
        # first arg is anything other than a constant string/number.
        if node.args and isinstance(node.args[0], ast.Constant):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="eval-usage",
                category="Security",
                severity="error",
                tier="P0",
                source="native",
                confidence="high",
                title=f"Use of builtin {node.func.id}() on dynamic input",
                message=(
                    f"'{node.func.id}()' at line {node.lineno} executes "
                    "arbitrary code and is a remote-code-execution risk."
                ),
                help=(
                    "Avoid eval/exec. For Odoo domains/expressions use "
                    "odoo.tools.safe_eval; otherwise refactor to explicit logic."
                ),
                odoo_version=odoo_version,
            )
        )
    return diags
