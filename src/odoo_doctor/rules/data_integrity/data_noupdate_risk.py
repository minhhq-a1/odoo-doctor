# src/odoo_doctor/rules/data_integrity/data_noupdate_risk.py
"""Rule: data-noupdate-risk [Data Integrity, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_CRITICAL_MODELS = {
    "ir.rule",
    "ir.config_parameter",
    "ir.cron",
}


@rule(
    name="data-noupdate-risk",
    category="Data Integrity",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_data_noupdate_risk(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag critical model records in XML data without noupdate='1'."""
    diags: list[Diagnostic] = []

    for rec in ctx.xml_records:
        if rec.model not in _CRITICAL_MODELS:
            continue
        if rec.noupdate:
            continue

        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=rec.file_path,
                line=rec.line,
                column=0,
                rule="data-noupdate-risk",
                category="Data Integrity",
                severity="warning",
                tier="P2",
                source="native",
                confidence="high",
                title=f"'{rec.model}' record without noupdate",
                message=f"Record '{rec.xml_id}' of model '{rec.model}' is not wrapped in noupdate='1'. It will be overwritten on every module update.",
                help="Wrap this record in <data noupdate='1'> to prevent overwriting user modifications.",
                odoo_version=ctx.odoo_version,
            )
        )

    return diags
