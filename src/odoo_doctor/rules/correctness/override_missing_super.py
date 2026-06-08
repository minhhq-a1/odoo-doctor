# src/odoo_doctor/rules/correctness/override_missing_super.py
"""Rule: override-missing-super [Correctness, P1]."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule
from odoo_doctor.parsers.python_models import parse_models


_TARGET_METHODS = {"create", "write", "unlink", "copy", "default_get"}


@rule(
    name="override-missing-super",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_override_missing_super(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    models = parse_models(file_path)
    for model in models:
        for method_name, method in model.methods.items():
            if method_name in _TARGET_METHODS and not method.calls_super:
                diags.append(
                    Diagnostic(
                        module=module_name,
                        file_path=str(file_path),
                        line=method.line,
                        column=0,
                        rule="override-missing-super",
                        category="Correctness",
                        severity="error",
                        tier="P1",
                        source="native",
                        confidence="high",
                        title=f"Override of '{method_name}' missing super() call",
                        message=f"Method '{method_name}' overrides a lifecycle method but never calls super().",
                        help=f"Add a call to super().{method_name}(...) and return its result.",
                        odoo_version=odoo_version,
                    )
                )

    return diags
