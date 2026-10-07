# src/odoo_doctor/rules/xml/orphan_view.py
"""Rule: orphan-view [Maintainability, P2]."""

from __future__ import annotations

import re

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule


def _short_id(xml_id: str) -> str:
    """Strip a leading 'module.' prefix from an xml id for local comparison."""
    return xml_id.split(".", 1)[1] if "." in xml_id else xml_id


_TEXT_SUFFIXES = frozenset({".py", ".xml", ".js", ".csv", ".json"})
_MAX_FILE_BYTES = 512 * 1024


def _module_text(ctx: ModuleContext) -> str:
    """Source text of the module's code and data files, for textual id references
    (``env.ref('m.view')``, ``form_view_ref`` in a context, JS ``doAction``)."""
    parts: list[str] = []
    for f in sorted(ctx.path.rglob("*")):
        if f.suffix not in _TEXT_SUFFIXES or not f.is_file():
            continue
        try:
            if f.stat().st_size > _MAX_FILE_BYTES:
                continue
            parts.append(f.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(parts)


def _mentioned_outside_definition(local_id: str, text: str) -> bool:
    """Does *local_id* appear in *text* other than as its own ``id="..."``?"""
    word = re.compile(rf"(?<![\w]){re.escape(local_id)}(?![\w])")
    definition = re.compile(rf"""\bid\s*=\s*["'](?:\w+\.)?{re.escape(local_id)}["']""")
    return len(word.findall(text)) > len(definition.findall(text))


@rule(
    name="orphan-view",
    category="Maintainability",
    tier="P2",
    severity="warning",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_orphan_view(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    # Collect every xml id referenced anywhere in this module (refs in records,
    # plus inherit_id targets from views).
    referenced: set[str] = set()
    for rec in ctx.xml_records:
        for ref in rec.refs:
            referenced.add(_short_id(ref))
    for view in ctx.views:
        if view.inherit_id:
            referenced.add(_short_id(view.inherit_id))

    # Odoo serves a model's primary view of each type on its own (lowest priority, then
    # first defined), with no action or reference involved. Only the other primary
    # views can be dead.
    primary: dict[tuple[str, str], list] = {}
    for view in ctx.views:
        if view.inherit_id or view.view_type in (None, "qweb"):
            continue
        primary.setdefault((view.model, view.view_type), []).append(view)
    candidates = []
    for views in primary.values():
        default = min(views, key=lambda v: v.priority)  # min() keeps the first on a tie
        candidates.extend(v for v in views if v is not default)

    text: str | None = None
    for view in candidates:
        local_id = _short_id(view.xml_id)
        if local_id in referenced:
            continue
        if text is None:
            text = _module_text(ctx)
        if _mentioned_outside_definition(local_id, text):
            continue
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="orphan-view",
                category="Maintainability",
                severity="warning",
                tier="P2",
                source="native",
                confidence="medium",
                title=f"View '{local_id}' is not referenced",
                message=(
                    f"View '{view.xml_id}' for model '{view.model}' is not the "
                    f"default {view.view_type} view and nothing in the module "
                    "references or inherits it."
                ),
                help=(
                    "Reference the view from an action's view_id, inherit it, "
                    "or remove it if unused. (Medium confidence: the reference "
                    "may live in a module not scanned here.)"
                ),
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
