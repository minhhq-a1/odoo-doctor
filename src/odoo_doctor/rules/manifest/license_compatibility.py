# src/odoo_doctor/rules/manifest/license_compatibility.py
"""Rule: manifest-license-incompatible [Module Hygiene, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Manifest `license` values (lower-cased) -> license family.
_FAMILY = {
    "gpl-2": "gpl2",  # version 2 only
    "gpl-2 or any later version": "gpl2+",
    "gpl-3": "gpl3",
    "gpl-3 or any later version": "gpl3+",
    "agpl-3": "agpl3",
    "lgpl-3": "lgpl3",
    "opl-1": "proprietary",
    "oeel-1": "proprietary",
    "other proprietary": "proprietary",
}

_V3_ONLY = {"gpl3", "agpl3", "lgpl3"}
_V3_OR_LATER = _V3_ONLY | {"gpl3+"}
_STRONG_COPYLEFT = {"gpl2", "gpl2+", "gpl3", "gpl3+", "agpl3"}


def _family(license_name: str | None) -> str | None:
    return _FAMILY.get(license_name.strip().lower()) if license_name else None


def _conflict(mine: str, dep: str) -> tuple[str, str] | None:
    """(confidence, reason) when `mine` depends on a module licensed `dep`."""
    # GPL-2-only code cannot be combined with GPL-3-family code, in either direction.
    if mine == "gpl2" and dep in _V3_OR_LATER:
        return (
            "high",
            "GPL-2 (version 2 only) cannot be combined with GPL-3 family code",
        )
    if dep == "gpl2" and mine in _V3_OR_LATER:
        return (
            "high",
            "GPL-3 family code cannot be combined with GPL-2 (version 2 only)",
        )
    # A proprietary module that depends on a strong-copyleft one is a legal grey
    # area (the combination may count as a derived work): worth a human look.
    if mine == "proprietary" and dep in _STRONG_COPYLEFT:
        return (
            "medium",
            (
                "a proprietary module depends on strong-copyleft code, which may make "
                "the combination a derived work"
            ),
        )
    return None


@rule(
    name="manifest-license-incompatible",
    category="Module Hygiene",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_license_incompatible(ctx: ModuleContext) -> list[Diagnostic]:
    """Compare the addon's license with the licenses of its scanned dependencies."""
    diags: list[Diagnostic] = []
    mine_name = ctx.manifest.raw.get("license")
    mine = _family(str(mine_name)) if mine_name else None
    if mine is None:
        return diags

    manifest_file = str(ctx.path / "__manifest__.py")
    for dep in ctx.depends:
        dep_name = ctx.resolver.module_license(dep)
        dep_family = _family(dep_name)
        if dep_family is None:
            continue
        found = _conflict(mine, dep_family)
        if found is None:
            continue
        confidence, reason = found
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=manifest_file,
                line=1,
                column=0,
                rule="manifest-license-incompatible",
                category="Module Hygiene",
                severity="warning",
                tier="P2",
                source="native",
                confidence=confidence,
                title=f"License '{mine_name}' vs dependency '{dep}' ({dep_name})",
                message=(
                    f"'{ctx.name}' is licensed {mine_name} but depends on '{dep}', "
                    f"licensed {dep_name}: {reason}."
                ),
                help=(
                    "Relicense one of the modules, or remove the dependency. "
                    "Check with whoever owns the licensing before shipping."
                ),
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
