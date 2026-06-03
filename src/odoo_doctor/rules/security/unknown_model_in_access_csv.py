# src/odoo_doctor/rules/security/unknown_model_in_access_csv.py
"""Rule: unknown-model-in-access-csv [Security, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.parsers.security_csv import model_external_id_to_name
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="unknown-model-in-access-csv",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_unknown_model_in_access_csv(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag access rules that reference models not found in the codebase or stubs."""
    diags: list[Diagnostic] = []

    for rule_row in ctx.access_rules:
        model_name = model_external_id_to_name(rule_row.model_external_id)
        result = ctx.resolver.resolve_model(model_name)

        if result.status == ResolveResult.NOT_FOUND:
            confidence = "high"
        elif (
            result.status == ResolveResult.UNKNOWN
            and rule_row.model_external_id_module == ctx.name
        ):
            # The CSV points at an ir.model external ID in the current module.
            # The project graph has already parsed every local model, so absence
            # here is actionable even though the generic resolver is conservative.
            confidence = "high"
        elif result.status == ResolveResult.UNKNOWN:
            continue  # Don't emit for UNKNOWN — could be from an unscanned dependency.
        else:
            continue

        diags.append(Diagnostic(
            module=ctx.name,
            file_path=rule_row.file_path,
            line=rule_row.line,
            column=0,
            rule="unknown-model-in-access-csv",
            category="Security",
            severity="error",
            tier="P1",
            source="native",
            confidence=confidence,
            title=f"Access rule references unknown model: {model_name}",
            message=f"The access rule '{rule_row.id}' references model '{model_name}' which cannot be found.",
            help="Verify the model name in ir.model.access.csv matches the actual model _name.",
            odoo_version=ctx.odoo_version,
        ))

    return diags
