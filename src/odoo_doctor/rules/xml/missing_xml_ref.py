# src/odoo_doctor/rules/xml/missing_xml_ref.py
"""Rule: missing-xml-ref [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-xml-ref",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_xml_ref(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for xml_id, info in ctx.xml_ids.items():
        for ref in info.refs:
            qualified = ref if "." in ref else f"{ctx.name}.{ref}"
            lookup = ctx.resolver.resolve_xml_id_for_module(qualified, ctx.name)

            if lookup.status in (
                ResolveResult.NOT_FOUND,
                ResolveResult.LOCAL_NOT_FOUND,
            ):
                confidence = "high"
            else:
                continue

            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=info.file_path,
                    line=info.line,
                    column=0,
                    rule="missing-xml-ref",
                    category="Correctness",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence=confidence,
                    title=f"Unresolved XML reference: {ref}",
                    message=f"XML record '{xml_id}' references '{ref}' which cannot be resolved.",
                    help="Verify the referenced XML ID exists and the providing module is in depends.",
                    odoo_version=ctx.odoo_version,
                )
            )

    # Also check inherit_id refs in views
    for view in ctx.views:
        if view.inherit_id:
            qualified = (
                view.inherit_id
                if "." in view.inherit_id
                else f"{ctx.name}.{view.inherit_id}"
            )
            lookup = ctx.resolver.resolve_xml_id_for_module(qualified, ctx.name)
            if lookup.status not in (
                ResolveResult.NOT_FOUND,
                ResolveResult.LOCAL_NOT_FOUND,
            ):
                continue
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=view.file_path,
                    line=view.line,
                    column=0,
                    rule="missing-xml-ref",
                    category="Correctness",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"Unresolved inherit_id: {view.inherit_id}",
                    message=f"View '{view.xml_id}' inherits from '{view.inherit_id}' which cannot be resolved.",
                    help="Verify the parent view exists and the providing module is in depends.",
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
