# src/odoo_doctor/rules/correctness/monetary_missing_currency_field.py
"""Rule: monetary-missing-currency-field [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="monetary-missing-currency-field",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_monetary_missing_currency_field(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag `fields.Monetary` whose currency field provably does not exist."""
    diags: list[Diagnostic] = []

    for model_info in ctx.models.values():
        if model_info.name is None:
            continue
        # `_name` equal to `_inherit` extends an upstream model whose fields we may
        # not see; only models defined here are provably complete.
        if model_info.name in model_info.inherit:
            continue

        for fld in model_info.fields.values():
            if fld.field_type != "Monetary":
                continue
            currency_field = fld.currency_field or "currency_id"
            lookup = ctx.resolver.resolve_field(model_info.name, currency_field)
            if lookup.status != ResolveResult.NOT_FOUND:
                continue  # found, or not provable either way

            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=model_info.file_path,
                    line=fld.line,
                    column=0,
                    rule="monetary-missing-currency-field",
                    category="Correctness",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"Monetary field '{fld.name}' has no currency field",
                    message=(
                        f"Monetary field '{fld.name}' on model '{model_info.name}' "
                        f"uses currency field '{currency_field}', which does not "
                        "exist on the model."
                    ),
                    help=(
                        "Add a `currency_id = fields.Many2one('res.currency')` field "
                        "or point `currency_field=` at an existing Many2one to "
                        "res.currency."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
