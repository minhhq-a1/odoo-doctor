# src/odoo_doctor/rules/xml/duplicate_xml_id.py
"""Rule: duplicate-xml-id [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext
    from odoo_doctor.parsers.xml_records import XmlIdInfo


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
    """Report a later declaration of an id unless it only patches the record.

    Odoo loads a repeated id as an update of the same record (``_load_records``), so a
    later declaration that sets fields the earlier ones did not is a normal idiom and is
    not reported. Setting a field again is allowed too but is a copy-paste smell
    (medium). Another ``model`` makes the install fail with a ValidationError (high).
    """
    by_id: dict[str, list[XmlIdInfo]] = {}
    for info in ctx.xml_records:
        by_id.setdefault(info.xml_id, []).append(info)

    diags: list[Diagnostic] = []
    for xml_id, infos in by_id.items():
        first = infos[0]
        written = set(first.field_names or ())
        for later in infos[1:]:
            confidence, why, help_ = _classify(first, later, written)
            written |= later.field_names or set()
            if confidence is None:
                continue
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=later.file_path,
                    line=later.line,
                    column=0,
                    rule="duplicate-xml-id",
                    category="Correctness",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence=confidence,
                    title=f"Duplicate XML ID: {xml_id}",
                    message=f"XML ID '{xml_id}' is defined multiple times. First at {first.file_path}:{first.line}. {why}",
                    help=help_,
                    odoo_version=ctx.odoo_version,
                )
            )

    return diags


def _classify(
    first: XmlIdInfo, later: XmlIdInfo, written: set[str]
) -> tuple[str | None, str, str]:
    """(confidence, reason, help) for *later*; confidence None when it only patches."""
    unknown = (
        None in (first.model, later.model)
        or first.field_names is None
        or later.field_names is None
    )
    if unknown:  # a tag we cannot read the fields of: keep the plain duplicate finding
        return "high", "", "Remove or rename the duplicate XML ID."
    # theme_* modules load <template> as theme.ir.ui.view, so compare without the prefix
    if (first.model or "").removeprefix("theme.") != (later.model or "").removeprefix(
        "theme."
    ):
        return (
            "high",
            (
                f"It is model '{later.model}' here but '{first.model}' there; "
                "Odoo refuses to load an id under another model."
            ),
            "Rename one of the XML IDs.",
        )
    again = sorted(written & (later.field_names or set()))
    if again:
        return (
            "medium",
            f"It sets {', '.join(again)} again.",
            "Merge the two declarations, or rename the XML ID if they are two records.",
        )
    return None, "", ""
