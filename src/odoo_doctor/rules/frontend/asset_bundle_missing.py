# src/odoo_doctor/rules/frontend/asset_bundle_missing.py
"""Rule: asset-bundle-missing [Frontend, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


# Directives of a bundle entry (`('prepend', path)`) and the position of the file each one
# adds. `include` names a bundle and `remove` points at a file that already exists
# elsewhere, so neither adds a file of this module.
_ADDED_PATH_INDEX = {"prepend": 0, "append": 0, "before": 1, "after": 1, "replace": 1}


def _added_path(entry: object) -> str | None:
    """The file path an assets entry adds, or None when it adds none we can check.

    An entry is a plain path or a directive tuple/list such as ``('after', target, path)``.
    """
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, (tuple, list)) or not entry:
        return None
    index = _ADDED_PATH_INDEX.get(entry[0])
    if index is None or len(entry) < index + 2:
        return None
    path = entry[index + 1]
    return path if isinstance(path, str) else None


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
        if not isinstance(file_list, (list, tuple)):
            continue
        for entry in file_list:
            asset_path = _added_path(entry)
            if asset_path is None:
                continue
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
