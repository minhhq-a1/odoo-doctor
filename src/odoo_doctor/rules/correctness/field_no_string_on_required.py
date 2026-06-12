# src/odoo_doctor/rules/correctness/field_no_string_on_required.py
"""Rule: field-no-string-on-required [Maintainability, P2]."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule


def _is_required(field) -> bool:
    return field.required


def _has_string(field) -> bool:
    return field.string is not None


@rule(
    name="field-no-string-on-required",
    category="Maintainability",
    tier="P2",
    severity="info",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_field_no_string_on_required(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for model in ctx.models.values():
        for field_name, field in model.fields.items():
            if not _is_required(field) or _has_string(field):
                continue
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=getattr(field, "file_path", "") or model.file_path,
                    line=getattr(field, "line", 0) or model.line,
                    column=0,
                    rule="field-no-string-on-required",
                    category="Maintainability",
                    severity="info",
                    tier="P2",
                    source="native",
                    confidence="medium",
                    title=f"Required field '{field_name}' has no explicit string",
                    message=(
                        f"Field '{field_name}' on model "
                        f"'{model.name or '|'.join(model.inherit)}' is required "
                        "but has no explicit string= label."
                    ),
                    help=(
                        'Add string="..." so the required field has a clear, '
                        "translatable label in the UI."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )
    return diags
