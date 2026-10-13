# src/odoo_doctor/rules/upgrade_safety/view_attrs_states_removed.py
"""Rule: view-attrs-states-removed [Upgrade Safety, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules._module_files import data_files
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_REMOVED_ATTRS = ("attrs", "states")


def _is_qweb(record: etree._Element, arch: etree._Element) -> bool:
    for f in record.findall("field"):
        if f.get("name") == "type" and (f.text or "").strip() == "qweb":
            return True
    root = next((c for c in arch if isinstance(c.tag, str)), None)
    if root is None:
        return True
    if root.tag == "t":
        return True
    return any(
        k.startswith("t-")
        for el in arch.iter()
        if isinstance(el.tag, str)
        for k in el.attrib
    )


def _offenders(arch: etree._Element) -> list[etree._Element]:
    found = []
    for el in arch.iter():
        if not isinstance(el.tag, str) or el is arch:
            continue
        has_attr = any(a in el.attrib for a in _REMOVED_ATTRS)
        # An empty <attribute name="states"/> removes the attribute from the parent view
        # (the way to port a pre-17 view), so only a non-empty one sets it.
        sets_attr = (
            el.tag == "attribute"
            and el.get("name") in _REMOVED_ATTRS
            and bool("".join(el.itertext()).strip())
        )
        if has_attr or sets_attr:
            found.append(el)
    return found


@rule(
    name="view-attrs-states-removed",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="17.0",
)
def check_view_attrs_states_removed(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag ``attrs`` / ``states`` in the architecture of an ``ir.ui.view`` record.

    Odoo 17 and later refuse the view ("Since 17.0, the attrs and states attributes
    are no longer used"), so the module cannot be installed or updated. QWeb templates
    are not checked.
    """
    diags: list[Diagnostic] = []
    for path in data_files(ctx):
        try:
            tree = etree.parse(str(path))
        except (etree.XMLSyntaxError, OSError):
            continue
        for record in tree.iter("record"):
            if record.get("model") != "ir.ui.view":
                continue
            arch = next(
                (f for f in record.findall("field") if f.get("name") == "arch"), None
            )
            if arch is None or _is_qweb(record, arch):
                continue
            offenders = _offenders(arch)
            if not offenders:
                continue
            names = sorted(
                {a for el in offenders for a in _REMOVED_ATTRS if a in el.attrib}
                | {el.get("name") for el in offenders if el.tag == "attribute"}
            )
            rec_id = record.get("id", "<anonymous>")
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(path),
                    line=int(offenders[0].sourceline or record.sourceline or 1),
                    column=0,
                    rule="view-attrs-states-removed",
                    category="Upgrade Safety",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"View '{rec_id}' still uses {'/'.join(names)}",
                    message=(
                        f"View '{rec_id}' has {len(offenders)} element(s) with "
                        f"{' / '.join(names)}. Odoo 17 and later reject the view, so "
                        "the module fails to install or update."
                    ),
                    help=(
                        "Move the condition into the attribute itself: "
                        "attrs=\"{'invisible': [('state', '=', 'draft')]}\" becomes "
                        'invisible="state == \'draft\'"; states="draft" becomes '
                        "invisible=\"state != 'draft'\"."
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )
    return diags
