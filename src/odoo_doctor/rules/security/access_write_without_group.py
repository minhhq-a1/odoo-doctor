# src/odoo_doctor/rules/security/access_write_without_group.py
"""Rule: access-write-without-group [Security, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.parsers.security_csv import candidate_model_names
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="access-write-without-group",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_access_write_without_group(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag ir.model.access.csv rows that grant write/create/unlink to no group at all.

    An empty ``group_id:id`` makes the row global: it applies to every user, portal and
    public ones included. Throw-away wizard (transient) models are skipped. A row that
    only lets everyone *create* is reported at medium confidence, because public forms
    do that on purpose.
    """
    transient = {name for name, info in ctx.models.items() if info.is_transient}
    diags: list[Diagnostic] = []

    for row in ctx.access_rules:
        if row.group_id:
            continue
        if not (row.perm_write or row.perm_unlink or row.perm_create):
            continue
        if any(c in transient for c in candidate_model_names(row.model_external_id)):
            continue

        destructive = row.perm_write or row.perm_unlink
        granted = [
            name
            for name, on in (
                ("write", row.perm_write),
                ("create", row.perm_create),
                ("unlink", row.perm_unlink),
            )
            if on
        ]
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=row.file_path,
                line=row.line,
                column=0,
                rule="access-write-without-group",
                category="Security",
                severity="error",
                tier="P1",
                source="native",
                confidence="high" if destructive else "medium",
                title=f"Access rule '{row.id}' grants {'/'.join(granted)} to everyone",
                message=(
                    f"Row '{row.id}' ({row.model_external_id}) has no group_id, so "
                    f"{', '.join(granted)} apply to every user, including portal and "
                    "public users."
                ),
                help="Set group_id:id to base.group_user or a dedicated group.",
                odoo_version=ctx.odoo_version,
            )
        )

    return diags
