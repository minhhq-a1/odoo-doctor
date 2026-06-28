# src/odoo_doctor/rules/frontend/asset_bundle_missing.py
"""Rule: asset-bundle-missing [Frontend, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="asset-bundle-missing",
    category="Frontend",
    tier="P2",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="15.0",
)
def check_asset_bundle_missing(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag asset files listed in manifest that don't exist on disk."""
    diags: list[Diagnostic] = []

    if not ctx.manifest.assets:
        return diags

    for bundle_name, file_list in ctx.manifest.assets.items():
        for asset_path in file_list:
            # Skip glob patterns, URLs, and prepend/append directives
            if any(c in asset_path for c in ("*", "?", "://")) or asset_path.startswith(
                ("(", ")")
            ):
                continue

            # Strip prepend/append wrapping if present
            clean_path = asset_path.strip()

            # Asset paths in Odoo are relative to the addons root,
            # e.g., "my_module/static/src/..."
            # The first segment should be the module name
            parts = clean_path.split("/", 1)
            if len(parts) < 2:
                continue

            module_prefix = parts[0]
            relative_path = parts[1]

            # Only check assets for this module
            if module_prefix != ctx.name:
                continue

            full_path = ctx.path / relative_path
            if not full_path.exists():
                diags.append(
                    Diagnostic(
                        module=ctx.name,
                        file_path=str(ctx.path / "__manifest__.py"),
                        line=1,
                        column=0,
                        rule="asset-bundle-missing",
                        category="Frontend",
                        severity="error",
                        tier="P2",
                        source="native",
                        confidence="high",
                        title=f"Asset file not found: {clean_path}",
                        message=(
                            f"Asset '{clean_path}' in bundle '{bundle_name}' "
                            "does not exist on disk."
                        ),
                        help=(
                            f"Create the file at '{relative_path}' or remove "
                            "the reference from the manifest assets."
                        ),
                        odoo_version=ctx.odoo_version,
                    )
                )

    return diags
