# src/odoo_doctor/rules/upgrade_safety/chatter_div_removed.py
"""Rule: chatter-div-removed [Upgrade Safety, P1]."""

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
    from lxml import etree

    from odoo_doctor.graph.module_context import ModuleContext

# The fields Odoo 17 put in the div; <chatter/> brings all of them by itself.
CHATTER_FIELDS = frozenset({"message_follower_ids", "activity_ids", "message_ids"})


def is_plain_chatter_div(div: etree._Element, arch: etree._Element) -> bool:
    """Can ``<chatter/>`` replace this div without losing anything or changing meaning?

    Only the class, only the standard chatter fields inside (or nothing), and a place
    where Odoo 18 and 19 themselves put ``<chatter/>``: directly under the root of the
    arch, or in the body of an ``xpath`` of an inheriting view. Anything else is for a
    person to look at.
    """
    root = next((c for c in arch if isinstance(c.tag, str)), None)
    parent = div.getparent()
    return (
        dict(div.attrib) == {"class": div.get("class", "")}
        and div.get("class", "").split() == ["oe_chatter"]
        and (parent is root or (parent is not None and parent.tag == "xpath"))
        and not (div.text or "").strip()
        and all(
            c.tag == "field"
            and c.get("name") in CHATTER_FIELDS
            and len(c) == 0
            and not (c.tail or "").strip()
            for c in div
        )
    )


@rule(
    name="chatter-div-removed",
    category="Upgrade Safety",
    tier="P1",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    fixable=True,
    min_version="18.0",
)
def check_chatter_div_removed(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag ``<div class="oe_chatter">`` in a view; Odoo 18 uses the ``<chatter/>`` tag.

    The form compiler of Odoo 17 selected ``div.oe_chatter``. Odoo 18 and 19 select only
    the ``chatter`` tag, so the div is rendered as a plain block and the form has no
    chatter. The view still loads, so nothing fails at install time.

    ``high`` when every such div is plain (``is_plain_chatter_div``): ``fix --upgrade-to``
    replaces it by ``<chatter/>``. A div with other attributes or content, or in an
    unusual place, is ``medium``: the replacement would drop something.
    """
    diags: list[Diagnostic] = []
    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for record, arch in view_arches(tree):
            offenders = [
                e
                for e in elements(arch)
                if e.tag == "div" and "oe_chatter" in e.get("class", "").split()
            ]
            if not offenders:
                continue
            rec_id = record.get("id", "<anonymous>")
            plain = all(is_plain_chatter_div(e, arch) for e in offenders)
            diags.append(
                make_diag(
                    ctx=ctx,
                    path=path,
                    line=line_of(offenders[0], record),
                    rule="chatter-div-removed",
                    category="Upgrade Safety",
                    tier="P1",
                    severity="warning",
                    confidence="high" if plain else "medium",
                    title=f"View '{rec_id}' uses div.oe_chatter",
                    message=(
                        f"View '{rec_id}' adds the chatter with <div class=\"oe_chatter\">. "
                        "Odoo 18 and later only compile the <chatter/> tag, so this form "
                        "renders without followers, messages or activities."
                    ),
                    help='Replace the whole <div class="oe_chatter">...</div> block with '
                    "<chatter/>. It brings the follower, message and activity widgets of "
                    "mail.thread by itself.",
                )
            )
    return diags
