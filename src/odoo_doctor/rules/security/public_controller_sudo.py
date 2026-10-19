# src/odoo_doctor/rules/security/public_controller_sudo.py
"""Rule: public-controller-sudo-risk [Security, P1]."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.parsers.python_models import ControllerInfo, parse_controllers
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


def _diagnostics(
    controllers: list[ControllerInfo], module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for ctrl in controllers:
        if ctrl.auth not in ("public", "none", "unknown") or not ctrl.uses_sudo:
            continue
        # `auth=` written on the route is a decision of its author; an auth taken from the
        # overridden route (or one that cannot be resolved) is graded one step lower: Odoo's
        # own addons override public routes and elevate in them as a convention (6 of the 6
        # public overrides that call sudo() in core 19 were reviewed so).
        written = ctrl.declared_auth in ("public", "none")
        if written:
            confidence = "medium" if ctrl.guarded else "high"
            subject = f"is declared with auth='{ctrl.auth}'"
        else:
            confidence = "low" if ctrl.guarded else "medium"
            if ctrl.auth != "unknown":
                subject = f"inherits auth='{ctrl.auth}' from the route it overrides"
            elif ctrl.declared_auth is None:
                subject = (
                    "inherits its auth from a parent route that is not in the "
                    "scanned code"
                )
            else:
                subject = "computes its auth"
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=ctrl.file_path,
                line=ctrl.line,
                column=0,
                rule="public-controller-sudo-risk",
                category="Security",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title="Public controller route calls .sudo()"
                if ctrl.auth != "unknown"
                else "Route that may be public calls .sudo()",
                message=(
                    f"Controller method '{ctrl.method_name}' {subject} and uses .sudo()"
                    + (
                        ", after what looks like an access check (token, "
                        "signature or record access check)."
                        if ctrl.guarded
                        else " with no recognised access check in the route."
                    )
                ),
                help=(
                    "Review if sudo is necessary. Public routes with sudo bypass "
                    "access rights and can lead to privilege escalation: check "
                    "an access token (consteq on the record's access_token) or "
                    "the record access before elevating, and elevate the "
                    "narrowest recordset."
                    + (
                        " State auth= on the route so that it is not inherited."
                        if not written
                        else ""
                    )
                ),
                odoo_version=odoo_version,
            )
        )
    return diags


def check_public_controller_sudo(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """The routes of one file, with route inheritance resolved inside that file only."""
    return _diagnostics(parse_controllers(file_path), module_name, odoo_version)


@rule(
    name="public-controller-sudo-risk",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_public_controller_sudo_in_module(ctx: ModuleContext) -> list[Diagnostic]:
    # needs the project graph: an override with a bare @route() keeps its parent's auth
    return _diagnostics(ctx.controllers, ctx.name, ctx.odoo_version)
