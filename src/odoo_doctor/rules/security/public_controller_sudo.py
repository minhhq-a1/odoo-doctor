# src/odoo_doctor/rules/security/public_controller_sudo.py
"""Rule: public-controller-sudo-risk [Security, P1]."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.parsers.python_models import parse_controllers
from odoo_doctor.rules.registry import rule


@rule(
    name="public-controller-sudo-risk",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_public_controller_sudo(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    controllers = parse_controllers(file_path)
    for ctrl in controllers:
        if ctrl.auth in ("public", "none") and ctrl.uses_sudo:
            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=str(file_path),
                    line=ctrl.line,
                    column=0,
                    rule="public-controller-sudo-risk",
                    category="Security",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="medium" if ctrl.guarded else "high",
                    title="Public controller route calls .sudo()",
                    message=(
                        f"Controller method '{ctrl.method_name}' is declared with "
                        f"auth='{ctrl.auth}' and uses .sudo()"
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
                    ),
                    odoo_version=odoo_version,
                )
            )

    return diags
