# src/odoo_doctor/rules/xml/button_method_not_found.py
"""Rule: button-method-not-found [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="button-method-not-found",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_button_method_not_found(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for view in ctx.views:
        if not view.model:
            continue

        for method_name in view.button_methods:
            lookup = ctx.resolver.resolve_method(view.model, method_name)

            if lookup.status == ResolveResult.FOUND:
                continue
            if lookup.status == ResolveResult.NOT_FOUND:
                confidence = "high"
            else:
                continue

            diags.append(Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="button-method-not-found",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"Button calls unknown method '{method_name}'",
                message=f"View '{view.xml_id}' has button calling '{method_name}' on model '{view.model}' which is not found.",
                help=f"Add method '{method_name}' to model '{view.model}' or fix the button name attribute.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
