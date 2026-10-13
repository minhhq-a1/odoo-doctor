# src/odoo_doctor/rules/upgrade_safety/search_view_group_attributes.py
"""Rule: search-view-group-attributes [Upgrade Safety, P1]."""

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

# Attributes the Odoo 18 schema allowed on a search <group> and the 19 one rejects.
_REJECTED = ("string", "expand")


def _search_groups(arch):
    """``<group>`` elements that sit in a search view (root ``search``, or a filter inside)."""
    root = next((c for c in arch if isinstance(c.tag, str)), None)
    is_search = root is not None and root.tag == "search"
    for group in elements(arch):
        if group.tag != "group":
            continue
        if is_search or any(
            isinstance(child.tag, str) and child.tag == "filter" for child in group
        ):
            yield group


@rule(
    name="search-view-group-attributes",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="19.0",
)
def check_search_view_group_attributes(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag ``string`` / ``expand`` on a ``<group>`` of a search view.

    The Odoo 19 schema for that element dropped both attributes (``expand`` and
    ``string`` are still valid in 18), so the view is rejected on install or update.
    """
    diags: list[Diagnostic] = []
    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for record, arch in view_arches(tree):
            offenders = [
                g for g in _search_groups(arch) if any(a in g.attrib for a in _REJECTED)
            ]
            if not offenders:
                continue
            names = sorted({a for g in offenders for a in _REJECTED if a in g.attrib})
            rec_id = record.get("id", "<anonymous>")
            diags.append(
                make_diag(
                    ctx=ctx,
                    path=path,
                    line=line_of(offenders[0], record),
                    rule="search-view-group-attributes",
                    category="Upgrade Safety",
                    tier="P1",
                    severity="error",
                    title=f"Search view '{rec_id}' sets {'/'.join(names)} on a group",
                    message=(
                        f"{len(offenders)} <group> element(s) of search view '{rec_id}' "
                        f"carry {' / '.join(names)}. The Odoo 19 search view schema no "
                        "longer allows them, so the view is rejected."
                    ),
                    help='Use a bare <group> for the "Group By" filters: remove the '
                    "string and expand attributes.",
                )
            )
    return diags
