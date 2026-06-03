# src/odoo_doctor/rules/manifest/missing_dependency.py
"""Rule: manifest-missing-dependency [Module Hygiene, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


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
    """Check for models in _inherit that aren't in the manifest depends."""
    diags: list[Diagnostic] = []
    depends_set = set(ctx.depends)
    manifest_file = str(ctx.path / "__manifest__.py")

    # Check each model's _inherit list to see if its source module is in depends
    # For models defined in this module that inherit from external models,
    # we look for obvious patterns: if the inherited model's namespace doesn't
    # match any declared dependency's known namespace.
    # This is a heuristic check: we verify known prefixes from stubs.
    if ctx.resolver._stubs is None:
        return []

    module_to_models: dict[str, set[str]] = {}
    for model_name, stub_data in ctx.resolver._stubs.models.items():
        # Best effort: infer module from model prefix
        prefix = model_name.split(".")[0]
        module_to_models.setdefault(prefix, set()).add(model_name)

    from odoo_doctor.graph.resolver import ResolveResult

    for model_info in ctx.models.values():
        # Only check inherit-only models (they have _inherit but no _name)
        # or models that inherit from external models
        for inherited in model_info.inherit:
            # Check if the inherited model is defined in this repo with its own _name
            # (meaning it's a local model definition, not external)
            inherited_in_repo = any(
                m.name == inherited
                for m in ctx.models.values()
                if m.name is not None
            )
            if inherited_in_repo:
                continue

            # Lookup the inherited model in stubs only
            result = ctx.resolver.resolve_model(inherited)
            if result.status != ResolveResult.FOUND or result.source != "stub":
                continue

            # Infer module from model name prefix
            prefix = inherited.split(".")[0]
            # Skip trivial base prefixes
            if prefix in ("base", "ir", "res", "mail"):
                continue

            # If prefix as a module name isn't in depends — flag it
            if prefix not in depends_set:
                diags.append(Diagnostic(
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
                    title=f"Possible missing dependency for '{inherited}'",
                    message=f"Model '{inherited}' is inherited but module '{prefix}' is not in depends.",
                    help=f"Add '{prefix}' to the 'depends' list in __manifest__.py.",
                    odoo_version=ctx.odoo_version,
                ))

    return diags
