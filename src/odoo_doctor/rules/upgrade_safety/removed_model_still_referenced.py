# src/odoo_doctor/rules/upgrade_safety/removed_model_still_referenced.py
"""Rule: removed-model-still-referenced [Upgrade Safety, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


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
    """Flag models inherited/referenced that cannot be resolved in the project or stubs."""
    diags: list[Diagnostic] = []

    for model_info in ctx.models.values():
        for inherited in model_info.inherit:
            # Skip self-inheritance (model inherits itself to extend)
            if inherited == model_info.name:
                continue

            lookup = ctx.resolver.resolve_model(inherited)

            if lookup.status == ResolveResult.FOUND:
                continue

            # NOT_FOUND means provably absent (complete model set available).
            # UNKNOWN means we cannot prove existence — could be a removed model,
            # an unscanned third-party dependency, or a typo.  Either way, flag
            # with medium confidence so it won't affect scoring but is visible.
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
                    title=f"Model '{inherited}' not found in Odoo {ctx.odoo_version}",
                    message=(
                        f"Model '{inherited}' is inherited but could not be resolved "
                        f"in the project or Odoo {ctx.odoo_version} stubs. "
                        f"It may have been removed, renamed, or belongs to an "
                        f"unscanned dependency."
                    ),
                    help=(
                        f"Verify that '{inherited}' still exists in Odoo "
                        f"{ctx.odoo_version}. If it was removed or renamed, "
                        f"update your _inherit declaration."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
