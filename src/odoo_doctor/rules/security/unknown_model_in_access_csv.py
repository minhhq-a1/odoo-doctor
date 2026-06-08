# src/odoo_doctor/rules/security/unknown_model_in_access_csv.py
"""Rule: unknown-model-in-access-csv [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.parsers.security_csv import (
    candidate_model_names,
    model_external_id_to_name,
)
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="unknown-model-in-access-csv",
    category="Correctness",
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
        resolved = False
        for candidate in candidate_model_names(rule_row.model_external_id):
            if ctx.resolver.resolve_model(candidate).status == ResolveResult.FOUND:
                resolved = True
                break
        if resolved:
            continue

        # No candidate resolves. Only assert "unknown" for a model the row claims
        # belongs to THIS module (provable local absence); stay silent otherwise.
        if rule_row.model_external_id_module != ctx.name:
            continue

        model_name = model_external_id_to_name(rule_row.model_external_id)
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=rule_row.file_path,
                line=rule_row.line,
                column=0,
                rule="unknown-model-in-access-csv",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"Access rule references unknown model: {model_name}",
                message=f"The access rule '{rule_row.id}' references model '{model_name}' which cannot be found.",
                help="Verify the model name in ir.model.access.csv matches the actual model _name.",
                odoo_version=ctx.odoo_version,
            )
        )

    return diags
