# src/odoo_doctor/rules/upgrade_safety/act_window_target_inline.py
"""Rule: act-window-target-inline [Upgrade Safety, P1]."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._module_files import (
    data_files,
    field_of,
    field_text,
    line_of,
    make_diag,
    parse_xml,
    python_files,
    records,
)
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="act-window-target-inline",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="19.0",
)
def check_act_window_target_inline(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag an ``ir.actions.act_window`` whose ``target`` is ``inline``.

    Odoo 19 removed that value from the selection (``current``, ``new``, ``fullscreen``
    and ``main`` remain; the settings actions use ``current``), so the record is rejected
    on install or update.
    """
    diags: list[Diagnostic] = []

    def emit(path, line, what: str, confidence="high") -> None:
        diags.append(
            make_diag(
                ctx=ctx,
                path=path,
                line=line,
                rule="act-window-target-inline",
                category="Upgrade Safety",
                tier="P1",
                severity="error",
                confidence=confidence,
                title="Action target 'inline' was removed in Odoo 19",
                message=f"{what} sets target to 'inline', a value Odoo 19 removed from "
                "ir.actions.act_window.",
                help="Use target 'current' (the settings actions of Odoo 19 do), or "
                "'new' to open it in a dialog.",
            )
        )

    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for record in records(tree, "ir.actions.act_window"):
            if field_text(record, "target") == "inline":
                emit(
                    path,
                    line_of(field_of(record, "target"), record),
                    f"Action '{record.get('id', '<anonymous>')}'",
                )
    for path in python_files(ctx):
        py = parse_python(path)
        if py is None:
            continue
        for node in ast.walk(py):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value: v
                for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            target = keys.get("target")
            if not (isinstance(target, ast.Constant) and target.value == "inline"):
                continue
            action_type = keys.get("type")
            is_action = "res_model" in keys or (
                isinstance(action_type, ast.Constant)
                and action_type.value == "ir.actions.act_window"
            )
            if is_action:
                emit(path, node.lineno, "This action dict")
    return diags
