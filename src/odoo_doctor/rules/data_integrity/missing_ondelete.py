# src/odoo_doctor/rules/data_integrity/missing_ondelete.py
"""Rule: missing-ondelete [Data Integrity, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-ondelete",
    category="Data Integrity",
    tier="P1",
    severity="warning",
    default_confidence="low",
    needs_context=True,
    min_version="14.0",
)
def check_missing_ondelete(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag optional stored Many2one fields without explicit ondelete (advisory)."""
    diags: list[Diagnostic] = []

    for model_info in ctx.models.values():
        if model_info.is_transient or model_info.is_abstract:
            continue
        if model_info.name is None:
            continue

        for field in model_info.fields.values():
            if field.field_type != "Many2one":
                continue
            if field.ondelete is not None:
                continue
            # `ondelete` configures a foreign-key column; a related or computed Many2one
            # that is not stored has none.
            if not field.store:
                continue
            # Odoo defaults a required Many2one to 'restrict' ('set null' would be
            # rejected for it), so the default is already a deliberate-safe choice.
            if field.required:
                continue

            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=model_info.file_path,
                    line=field.line,
                    column=0,
                    rule="missing-ondelete",
                    category="Data Integrity",
                    severity="warning",
                    tier="P1",
                    source="native",
                    confidence="low",
                    title=f"Many2one '{field.name}' has no explicit ondelete",
                    message=(
                        f"Field '{field.name}' on model '{model_info.name}' is a "
                        "Many2one without an explicit ondelete policy, so Odoo applies "
                        "'set null': deleting the target silently empties this field."
                    ),
                    help=(
                        "If that is intended nothing needs to change (Odoo's own "
                        "addons mostly rely on it). Use ondelete='cascade' for a line "
                        "that must not outlive its parent, or 'restrict' to forbid "
                        "deleting a target that is still referenced."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
