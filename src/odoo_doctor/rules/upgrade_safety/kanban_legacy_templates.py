# src/odoo_doctor/rules/upgrade_safety/kanban_legacy_templates.py
"""Rule: kanban-legacy-templates [Upgrade Safety, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules._module_files import (
    data_files,
    elements,
    line_of,
    make_diag,
    parse_xml,
    view_arches,
)
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_RENAMED = {"kanban-box": "card", "kanban-menu": "menu"}


@rule(
    name="kanban-legacy-templates",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="19.0",
)
def check_kanban_legacy_templates(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag the ``kanban-box`` / ``kanban-menu`` templates, named ``card`` / ``menu`` since 18.

    Odoo 18 still read the old names with a deprecation note; Odoo 19 reads only ``card``
    and ``menu`` and the kanban view fails with "Missing 'card' template". An XPath that
    targets the old name no longer finds its anchor in the core kanban view.
    """
    diags: list[Diagnostic] = []
    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for record, arch in view_arches(tree):
            offenders = []
            for el in elements(arch):
                if el.get("t-name") in _RENAMED:
                    offenders.append((el, el.get("t-name")))
                elif el.tag == "xpath":
                    expr = el.get("expr", "")
                    offenders.extend((el, n) for n in _RENAMED if n in expr)
            if not offenders:
                continue
            old = sorted({name for _, name in offenders})
            rec_id = record.get("id", "<anonymous>")
            diags.append(
                make_diag(
                    ctx=ctx,
                    path=path,
                    line=line_of(offenders[0][0], record),
                    rule="kanban-legacy-templates",
                    category="Upgrade Safety",
                    tier="P1",
                    severity="error",
                    title=f"Kanban view '{rec_id}' uses {' / '.join(old)}",
                    message=(
                        f"View '{rec_id}' still uses the legacy kanban template name(s) "
                        f"{', '.join(old)}. Odoo 19 reads only {', '.join(_RENAMED[n] for n in old)}: "
                        "the kanban view fails with \"Missing 'card' template\" and an "
                        "XPath on the old name matches nothing."
                    ),
                    help=(
                        'Rename t-name="kanban-box" to "card" and "kanban-menu" to '
                        '"menu", and port the card markup to the Odoo 18 card layout '
                        "(main / aside / footer). Re-anchor inherited XPaths on the new "
                        "structure."
                    ),
                )
            )
    return diags
