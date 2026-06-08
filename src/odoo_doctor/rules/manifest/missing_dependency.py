# src/odoo_doctor/rules/manifest/missing_dependency.py
"""Rule: manifest-missing-dependency [Module Hygiene, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


_ALWAYS_AVAILABLE = {"base", "ir", "res"}


def _module_from_external_id(xml_id: str) -> str | None:
    if "." not in xml_id:
        return None
    module, _name = xml_id.split(".", 1)
    return module or None


@rule(
    name="manifest-missing-dependency",
    category="Module Hygiene",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_dependency(ctx: ModuleContext) -> list[Diagnostic]:
    """Check for missing dependencies implied by _inherit, XML references, and inherited views."""
    diags: list[Diagnostic] = []
    depends_set = set(ctx.depends)
    manifest_file = str(ctx.path / "__manifest__.py")

    missing_deps: dict[str, list[str]] = {}

    # 1. Check Python model inherits
    for model_info in ctx.models.values():
        for inherited in model_info.inherit:
            lookup = ctx.resolver.owner_module_for_model(inherited)
            if lookup.status == ResolveResult.FOUND:
                owner_mod = lookup.source
                if (
                    owner_mod
                    and owner_mod != ctx.name
                    and owner_mod not in depends_set
                    and owner_mod not in _ALWAYS_AVAILABLE
                ):
                    missing_deps.setdefault(owner_mod, []).append(
                        f"Model inherit: '{inherited}'"
                    )

    # 2. Check XML ID refs
    for rec in ctx.xml_records:
        for ref in rec.refs:
            mod = _module_from_external_id(ref)
            if (
                mod
                and ctx.resolver.module_is_known(mod)
                and mod != ctx.name
                and mod not in depends_set
                and mod not in _ALWAYS_AVAILABLE
            ):
                missing_deps.setdefault(mod, []).append(
                    f"XML ref in record '{rec.xml_id}': '{ref}'"
                )

    # 3. Check inherited views
    for view in ctx.views:
        if view.inherit_id:
            mod = _module_from_external_id(view.inherit_id)
            if (
                mod
                and ctx.resolver.module_is_known(mod)
                and mod != ctx.name
                and mod not in depends_set
                and mod not in _ALWAYS_AVAILABLE
            ):
                missing_deps.setdefault(mod, []).append(
                    f"Inherited view in view '{view.xml_id}': '{view.inherit_id}'"
                )

    # Emit aggregated diagnostics
    for missing_mod, evidences in sorted(missing_deps.items()):
        # Deduplicate evidences
        unique_evidences = []
        for ev in evidences:
            if ev not in unique_evidences:
                unique_evidences.append(ev)

        evidence_str = ", ".join(unique_evidences)
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=manifest_file,
                line=1,
                column=0,
                rule="manifest-missing-dependency",
                category="Module Hygiene",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"Possible missing dependency for '{missing_mod}'",
                message=f"Module '{missing_mod}' is required but not listed in depends. Evidence: {evidence_str}.",
                help=f"Add '{missing_mod}' to the 'depends' list in __manifest__.py.",
                odoo_version=ctx.odoo_version,
            )
        )

    return diags
