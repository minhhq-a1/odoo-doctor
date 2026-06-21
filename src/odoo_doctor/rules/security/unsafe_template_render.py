# src/odoo_doctor/rules/security/unsafe_template_render.py
"""Rule: unsafe-template-render [Security, P1]."""

from __future__ import annotations

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule

# QWeb directives that emit their value WITHOUT HTML-escaping it. ``t-raw`` was
# the historical one (removed in 17.0); ``t-out`` only renders raw markup when
# paired with ``t-options`` widget/html or a Markup value, but a bare attribute
# of ``t-raw`` is unambiguously unescaped output -> stored/reflected XSS risk.
_UNSAFE_ATTR = "t-raw"

# ``t-raw="0"`` is the canonical, SAFE idiom that renders the body passed into a
# ``t-call`` template; it never carries user data, so it must not be flagged.
_SAFE_VALUES = {"0"}


@rule(
    name="unsafe-template-render",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_unsafe_template_render(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for data_file in ctx.manifest.data:
        xml_path = ctx.path / data_file
        if xml_path.suffix != ".xml" or not xml_path.exists():
            continue
        try:
            tree = etree.parse(str(xml_path))
        except etree.XMLSyntaxError:
            continue

        for elem in tree.getroot().iter():
            # Skip comments / processing instructions (their .tag is callable).
            if not isinstance(elem.tag, str):
                continue
            value = elem.get(_UNSAFE_ATTR)
            if value is None or value.strip() in _SAFE_VALUES:
                continue
            line = elem.sourceline or 0
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(xml_path),
                    line=line,
                    column=0,
                    rule="unsafe-template-render",
                    category="Security",
                    severity="warning",
                    tier="P1",
                    source="native",
                    confidence="medium",
                    title=f"Unescaped QWeb output via {_UNSAFE_ATTR}",
                    message=(
                        f'<{elem.tag} {_UNSAFE_ATTR}="{value}"> at line {line} '
                        "renders its value without HTML-escaping; if it can "
                        "contain user-controlled data this is an XSS risk."
                    ),
                    help=(
                        "Use t-esc (or t-out, Odoo 17+) so the value is escaped. "
                        "Only render raw markup when the value is a trusted "
                        "Markup object. (Medium confidence: the data source may "
                        "already be sanitized.)"
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags
