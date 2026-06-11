# src/odoo_doctor/rules/security/record_rule_without_domain.py
"""Rule: record-rule-without-domain [Security, P1]."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule

# Compared after removing ALL whitespace, so spacing variants collapse.
_OPEN_DOMAINS = {"", "[]", "[(1,'=',1)]"}


def _normalize_domain(text: str) -> str:
    return "".join(text.split())


@rule(
    name="record-rule-without-domain",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_record_rule_without_domain(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for data_file in ctx.manifest.data:
        path = ctx.path / data_file
        if path.suffix != ".xml" or not path.exists():
            continue
        try:
            tree = etree.parse(str(path))
        except (etree.XMLSyntaxError, OSError):
            continue
        for record in tree.iter("record"):
            if record.get("model") != "ir.rule":
                continue
            domain = None
            for field in record.findall("field"):
                if field.get("name") == "domain_force":
                    domain = (field.text or "").strip()
                    break
            if domain is None or _normalize_domain(domain) in _OPEN_DOMAINS:
                line = record.sourceline or 1
                rec_id = record.get("id", "<anonymous>")
                diags.append(
                    Diagnostic(
                        module=ctx.name,
                        file_path=str(path),
                        line=int(line),
                        column=0,
                        rule="record-rule-without-domain",
                        category="Security",
                        severity="warning",
                        tier="P1",
                        source="native",
                        confidence="medium",
                        title=f"ir.rule '{rec_id}' has no restricting domain",
                        message=(
                            f"Record rule '{rec_id}' defines no domain_force (or "
                            "an empty domain), granting unrestricted record access."
                        ),
                        help=(
                            "Add a domain_force expression that limits the records "
                            "this rule applies to, e.g. "
                            "[('user_id', '=', user.id)]."
                        ),
                        odoo_version=ctx.odoo_version,
                    )
                )
    return diags
