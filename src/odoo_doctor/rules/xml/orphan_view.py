# src/odoo_doctor/rules/xml/orphan_view.py
"""Rule: orphan-view [Maintainability, P2]."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule


def _short_id(xml_id: str) -> str:
    """Strip a leading 'module.' prefix from an xml id for local comparison."""
    return xml_id.split(".", 1)[1] if "." in xml_id else xml_id


@rule(
    name="orphan-view",
    category="Maintainability",
    tier="P2",
    severity="warning",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_orphan_view(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    # Collect every xml id referenced anywhere in this module (refs in records,
    # plus inherit_id targets from views).
    referenced: set[str] = set()
    for rec in ctx.xml_records:
        for ref in rec.refs:
            referenced.add(_short_id(ref))
    for view in ctx.views:
        if view.inherit_id:
            referenced.add(_short_id(view.inherit_id))

    for view in ctx.views:
        if view.inherit_id:
            continue  # inheriting views are used by definition
        local_id = _short_id(view.xml_id)
        if local_id in referenced:
            continue
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="orphan-view",
                category="Maintainability",
                severity="warning",
                tier="P2",
                source="native",
                confidence="medium",
                title=f"View '{local_id}' is not referenced",
                message=(
                    f"View '{view.xml_id}' for model '{view.model}' is not "
                    "referenced by any action or inherited by another view."
                ),
                help=(
                    "Reference the view from an action's view_id, inherit it, "
                    "or remove it if unused. (Medium confidence: the reference "
                    "may live in a module not scanned here.)"
                ),
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
