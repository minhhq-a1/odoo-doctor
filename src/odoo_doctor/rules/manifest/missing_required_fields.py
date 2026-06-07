# src/odoo_doctor/rules/manifest/missing_required_fields.py
"""Rule: manifest-missing-required-fields [Module Hygiene, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_REQUIRED_FIELDS = ["name", "version", "depends", "data", "installable", "license"]


@rule(
    name="manifest-missing-required-fields",
    category="Module Hygiene",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_required_fields(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    manifest_file = str(ctx.path / "__manifest__.py")

    for field_name in _REQUIRED_FIELDS:
        value = ctx.manifest.raw.get(field_name)
        if value is None or value == "":
            diags.append(Diagnostic(
                module=ctx.name,
                file_path=manifest_file,
                line=1,
                column=0,
                rule="manifest-missing-required-fields",
                category="Module Hygiene",
                severity="warning",
                tier="P2",
                source="native",
                confidence="high",
                title=f"Manifest missing required field: {field_name!r}",
                message=f"The __manifest__.py for '{ctx.name}' is missing or has empty field '{field_name}'.",
                help=f"Add '{field_name}' to your __manifest__.py.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
