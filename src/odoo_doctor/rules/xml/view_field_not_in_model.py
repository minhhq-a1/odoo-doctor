# src/odoo_doctor/rules/xml/view_field_not_in_model.py
"""Rule: view-field-not-in-model [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="view-field-not-in-model",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_view_field_not_in_model(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for view in ctx.views:
        if not view.model:
            continue

        for field_name in view.field_refs:
            lookup = ctx.resolver.resolve_field(view.model, field_name)

            if lookup.status == ResolveResult.FOUND:
                continue
            if lookup.status == ResolveResult.NOT_FOUND:
                confidence = "high"
            else:
                continue

            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=view.file_path,
                    line=view.field_ref_lines.get(field_name, view.line),
                    column=0,
                    rule="view-field-not-in-model",
                    category="Correctness",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence=confidence,
                    title=f"View references unknown field '{field_name}'",
                    message=f"View '{view.xml_id}' for model '{view.model}' references field '{field_name}' which is not found.",
                    help=f"Add field '{field_name}' to model '{view.model}' or remove it from the view.",
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
