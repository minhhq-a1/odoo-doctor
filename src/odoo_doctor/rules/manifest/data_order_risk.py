# src/odoo_doctor/rules/manifest/data_order_risk.py
"""Rule: manifest-data-order-risk [Module Hygiene, P2]."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule
from odoo_doctor.graph.module_context import ModuleContext


def _is_security_file(path_str: str) -> bool:
    p = Path(path_str)
    if "security" in p.parts:
        return True
    name = p.name
    if "ir.model.access" in name or "security" in name or "groups" in name:
        return True
    return False


def _is_view_action_file(path_str: str) -> bool:
    p = Path(path_str)
    parts = p.parts
    if any(d in parts for d in ("views", "report", "wizard")):
        return True
    name = p.name
    if any(k in name for k in ("view", "action", "menu")):
        return True
    return False


@rule(
    name="manifest-data-order-risk",
    category="Module Hygiene",
    tier="P2",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
    fixable=True,
)
def check_data_order_risk(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    first_view_idx = -1
    first_view_file = ""

    for idx, data_file in enumerate(ctx.manifest.data):
        if _is_security_file(data_file):
            if first_view_idx != -1 and idx > first_view_idx:
                manifest_path = ctx.path / "__manifest__.py"
                diags.append(
                    Diagnostic(
                        module=ctx.name,
                        file_path=str(manifest_path),
                        line=1,  # Baseline: report line 1
                        column=0,
                        rule="manifest-data-order-risk",
                        category="Module Hygiene",
                        severity="error",
                        tier="P2",
                        source="native",
                        confidence="high",
                        title="Security file loaded after views/actions",
                        message=f"Security file '{data_file}' is loaded after view/action file '{first_view_file}'.",
                        help="Move security files before views and actions in the 'data' list to ensure access rights are created first.",
                        odoo_version=ctx.odoo_version,
                    )
                )
        elif _is_view_action_file(data_file):
            if first_view_idx == -1:
                first_view_idx = idx
                first_view_file = data_file

    return diags
