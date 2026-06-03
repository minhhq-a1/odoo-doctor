# src/odoo_doctor/rules/xml/duplicate_xml_id.py
"""Rule: duplicate-xml-id [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="duplicate-xml-id",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_duplicate_xml_id(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    id_locations: dict[str, list[tuple[str, int]]] = {}
    for info in ctx.xml_records:
        id_locations.setdefault(info.xml_id, []).append((info.file_path, info.line))

    for xml_id, locations in id_locations.items():
        if len(locations) <= 1:
            continue
        for file_path, line in locations[1:]:
            diags.append(Diagnostic(
                module=ctx.name,
                file_path=file_path,
                line=line,
                column=0,
                rule="duplicate-xml-id",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"Duplicate XML ID: {xml_id}",
                message=f"XML ID '{xml_id}' is defined multiple times. First at {locations[0][0]}:{locations[0][1]}.",
                help="Remove or rename the duplicate XML ID.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
