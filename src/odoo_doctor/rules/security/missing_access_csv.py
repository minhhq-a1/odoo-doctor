# src/odoo_doctor/rules/security/missing_access_csv.py
"""Rule: missing-access-csv [Security, P0]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-access-csv",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_access_csv(ctx: ModuleContext) -> list[Diagnostic]:
    """Detect models defined without any access rule in ir.model.access.csv."""
    diags: list[Diagnostic] = []

    if not ctx.access_rules:
        # No CSV at all — flag each new model
        for model_info in ctx.models.values():
            if model_info.name is None:
                continue  # inherit-only models don't need their own ACL
            if model_info.is_abstract:
                continue
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(ctx.path / "security" / "ir.model.access.csv"),
                    line=1,
                    column=0,
                    rule="missing-access-csv",
                    category="Security",
                    severity="error",
                    tier="P0",
                    source="native",
                    confidence="high",
                    title=f"No access rules for model '{model_info.name}'",
                    message=f"Model '{model_info.name}' has no entry in ir.model.access.csv.",
                    help="Create security/ir.model.access.csv and add access rules for this model.",
                    odoo_version=ctx.odoo_version,
                )
            )
        return diags

    # Collect models that have access rules
    from odoo_doctor.parsers.security_csv import candidate_model_names

    covered_models: set[str] = set()
    for rule_row in ctx.access_rules:
        for candidate in candidate_model_names(rule_row.model_external_id):
            covered_models.add(candidate)

    # Flag new models not covered
    for model_info in ctx.models.values():
        if model_info.name is None:
            continue
        if model_info.is_abstract or model_info.is_transient:
            continue
        if model_info.name not in covered_models:
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(ctx.path / "security" / "ir.model.access.csv"),
                    line=1,
                    column=0,
                    rule="missing-access-csv",
                    category="Security",
                    severity="error",
                    tier="P0",
                    source="native",
                    confidence="high",
                    title=f"No access rule for model '{model_info.name}'",
                    message=f"Model '{model_info.name}' is not covered in ir.model.access.csv.",
                    help="Add an access rule entry for this model.",
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
