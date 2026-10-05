# src/odoo_doctor/rules/security/missing_multicompany_rule.py
"""Rule: missing-multicompany-rule [Security, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-multicompany-rule",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_missing_multicompany_rule(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag company-owned models that no `ir.rule` in the project protects."""
    diags: list[Diagnostic] = []

    for model_info in ctx.models.values():
        if model_info.name is None or model_info.is_transient or model_info.is_abstract:
            continue
        company = model_info.fields.get("company_id")
        if (
            company is None
            or company.field_type != "Many2one"
            or company.comodel != "res.company"
        ):
            continue
        if ctx.resolver.model_has_record_rule(model_info.name):
            continue

        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=model_info.file_path,
                line=company.line,
                column=0,
                rule="missing-multicompany-rule",
                category="Security",
                severity="warning",
                tier="P1",
                source="native",
                # Medium: the rule may live outside the scanned addons, so we cannot
                # prove records leak across companies.
                confidence="medium",
                title=f"Model '{model_info.name}' has company_id but no record rule",
                message=(
                    f"Model '{model_info.name}' has a company_id field but no ir.rule "
                    "in the scanned modules restricts it by company. Users of one "
                    "company can read and edit another company's records."
                ),
                help=(
                    "Add an ir.rule with domain "
                    "[('company_id', 'in', company_ids)] (use "
                    "['|', ('company_id', '=', False), ('company_id', 'in', "
                    "company_ids)] when company is optional)."
                ),
                odoo_version=ctx.odoo_version,
            )
        )

    return diags
