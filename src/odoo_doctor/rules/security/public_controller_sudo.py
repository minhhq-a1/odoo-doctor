# src/odoo_doctor/rules/security/public_controller_sudo.py
"""Rule: public-controller-sudo-risk [Security, P1]."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule
from odoo_doctor.parsers.python_models import parse_controllers


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
                    confidence="high",
                    title="Public controller route calls .sudo()",
                    message=f"Controller method '{ctrl.method_name}' is declared with auth='{ctrl.auth}' and uses .sudo().",
                    help="Review if sudo is necessary. Public routes with sudo bypass access rights and can lead to privilege escalation.",
                    odoo_version=odoo_version,
                )
            )

    return diags
