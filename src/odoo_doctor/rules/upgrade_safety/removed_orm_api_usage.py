# src/odoo_doctor/rules/upgrade_safety/removed_orm_api_usage.py
"""Rule: removed-orm-api-usage [Upgrade Safety, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import (
    is_migration_file,
    is_model_class,
    is_test_file,
)
from odoo_doctor.rules.registry import rule

# ORM method -> (first Odoo major without it, what to use instead). Only methods that the
# ORM source of that release no longer defines belong here.
_REMOVED: dict[str, tuple[int, str]] = {
    "fields_view_get": (17, "get_view() (or _get_view())"),
    "invalidate_cache": (17, "invalidate_model() or invalidate_recordset()"),
    "name_get": (18, "_compute_display_name (the field display_name)"),
}

_RECORD_ROOTS = {"self", "cls", "env", "request"}


def _major(version: str) -> int | None:
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def _receiver_kind(node: ast.expr) -> str:
    """``record`` (self / env rooted), ``super`` or ``other`` for a call's receiver."""
    while True:
        if isinstance(node, ast.Attribute):
            if node.attr == "env":
                return "record"
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "super":
                return "super"
            node = node.func
        else:
            break
    if isinstance(node, ast.Name) and node.id in _RECORD_ROOTS:
        return "record"
    return "other"


@rule(
    name="removed-orm-api-usage",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="17.0",
)
def check_removed_orm_api_usage(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag overrides and calls of ORM methods the running Odoo version no longer has.

    An override of a removed method is dead code (nothing calls it any more); a call
    raises AttributeError. A call whose receiver is not obviously a record is reported at
    medium confidence, because the object may be unrelated to the ORM.
    """
    major = _major(odoo_version)
    if major is None or (
        is_test_file(file_path, module_name)
        or is_migration_file(file_path, module_name)
    ):
        return []
    removed = {name: v for name, v in _REMOVED.items() if major >= v[0]}
    if not removed:
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []

    def emit(name: str, node: ast.AST, what: str, confidence: str) -> None:
        since, instead = removed[name]
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="removed-orm-api-usage",
                category="Upgrade Safety",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"{name}() was removed in Odoo {since}",
                message=(
                    f"{what} {name}(), which Odoo {since}.0 removed from the ORM. "
                    + (
                        "Nothing calls an override any more."
                        if what.startswith("Override")
                        else "The call raises AttributeError."
                    )
                ),
                help=f"Use {instead} instead.",
                odoo_version=odoo_version,
            )
        )

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not is_model_class(cls):
            continue
        for stmt in cls.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                stmt.name in removed
            ):
                emit(stmt.name, stmt, "Override of", "high")

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in removed
        ):
            continue
        kind = _receiver_kind(node.func.value)
        if kind == "super":
            continue  # the override that calls super() is already reported
        emit(
            node.func.attr,
            node,
            "Call to",
            "high" if kind == "record" else "medium",
        )
    return diags
