# src/odoo_doctor/rules/upgrade_safety/removed_model_still_referenced.py
"""Rule: removed-model-still-referenced [Upgrade Safety, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


# Core models Odoo removed or renamed: model -> (first version without it, replacement).
# Only models whose removal is certain belong here. A model that merely is not in the
# scanned set is usually an unscanned dependency (stock, mrp, enterprise, OCA...), so
# "cannot be resolved" is not evidence that it was removed.
_REMOVED_MODELS: dict[str, tuple[int, str]] = {
    "product.uom": (12, "uom.uom"),
    "hr.holidays": (12, "hr.leave / hr.leave.allocation"),
    "procurement.order": (12, "stock.rule / procurement.group"),
    "stock.pack.operation": (12, "stock.move.line"),
    "account.invoice": (13, "account.move"),
    "account.invoice.line": (13, "account.move.line"),
    "account.invoice.tax": (13, "account.move.line"),
    "account.register.payments": (13, "account.payment.register"),
    "account.abstract.payment": (13, "account.payment"),
    "stock.production.lot": (16, "stock.lot"),
    "mail.channel": (17, "discuss.channel"),
    "mail.channel.partner": (17, "discuss.channel.member"),
}


def _major(version: str) -> int | None:
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


@rule(
    name="removed-model-still-referenced",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_removed_model_still_referenced(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag `_inherit` of a core model Odoo removed or renamed before this version."""
    diags: list[Diagnostic] = []
    major = _major(ctx.odoo_version)
    if major is None:
        return diags

    for model_info in ctx.models.values():
        for inherited in model_info.inherit:
            removed = _REMOVED_MODELS.get(inherited)
            if removed is None or major < removed[0]:
                continue
            # A project (or stub/source index) that provides the model owns it.
            if ctx.resolver.resolve_model(inherited).status == ResolveResult.FOUND:
                continue
            since, replacement = removed
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=model_info.file_path,
                    line=model_info.line,
                    column=0,
                    rule="removed-model-still-referenced",
                    category="Upgrade Safety",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="medium",
                    title=f"Model '{inherited}' was removed in Odoo {since}.0",
                    message=(
                        f"Model '{inherited}' is inherited but Odoo removed it in "
                        f"{since}.0 and it is not defined in the scanned project."
                    ),
                    help=(
                        f"Port the code to '{replacement}'. (Medium confidence: a "
                        f"compatibility module outside the scan may still define "
                        f"'{inherited}'.)"
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
