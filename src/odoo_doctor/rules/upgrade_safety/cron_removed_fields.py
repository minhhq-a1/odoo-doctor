# src/odoo_doctor/rules/upgrade_safety/cron_removed_fields.py
"""Rule: cron-removed-fields [Upgrade Safety, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules._module_files import data_files
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_REMOVED_FIELDS = ("numbercall", "doall")


@rule(
    name="cron-removed-fields",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="18.0",
)
def check_cron_removed_fields(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag ``numbercall`` / ``doall`` on an ``ir.cron`` record (gone since Odoo 18)."""
    diags: list[Diagnostic] = []
    for path in data_files(ctx):
        try:
            tree = etree.parse(str(path))
        except (etree.XMLSyntaxError, OSError):
            continue
        for record in tree.iter("record"):
            if record.get("model") != "ir.cron":
                continue
            found = [
                f for f in record.findall("field") if f.get("name") in _REMOVED_FIELDS
            ]
            if not found:
                continue
            names = [f.get("name") for f in found]
            limited = next(
                (
                    (f.text or "").strip()
                    for f in found
                    if f.get("name") == "numbercall"
                    and (f.text or "").strip().lstrip("-").isdigit()
                    and int((f.text or "").strip()) > 0
                ),
                None,
            )
            note = (
                f" numbercall={limited} limited the number of runs; without the field "
                "the job will repeat on every interval."
                if limited
                else ""
            )
            rec_id = record.get("id", "<anonymous>")
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(path),
                    line=int(found[0].sourceline or record.sourceline or 1),
                    column=0,
                    rule="cron-removed-fields",
                    category="Upgrade Safety",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"ir.cron '{rec_id}' sets fields removed in Odoo 18",
                    message=(
                        f"Cron '{rec_id}' sets {', '.join(names)}, which ir.cron no "
                        f"longer has since Odoo 18.{note}"
                    ),
                    help=(
                        "Remove the fields. If the job must run a limited number of "
                        "times, have the method deactivate the cron itself."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )
    return diags
