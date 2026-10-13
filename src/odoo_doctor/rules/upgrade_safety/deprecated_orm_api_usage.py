# src/odoo_doctor/rules/upgrade_safety/deprecated_orm_api_usage.py
"""Rule: deprecated-orm-api-usage [Upgrade Safety, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import (
    is_migration_file,
    is_model_class,
    is_test_file,
    odoo_major,
    receiver_kind,
)
from odoo_doctor.rules.registry import rule

# ORM method -> (first Odoo major that marks it @api.deprecated, what to use instead).
# Only methods that the ORM source of that release still defines but deprecates belong
# here; the ones it no longer defines are `removed-orm-api-usage`. `self._cr` /
# `_uid` / `_context` are deprecated in 19 as well but left out on purpose: Odoo core
# still uses them and they would bury every other finding.
_DEPRECATED: dict[str, tuple[int, str]] = {
    "read_group": (
        19,
        "_read_group() in backend code, or formatted_read_group() for a formatted result",
    ),
    "check_access_rights": (18, "check_access() (or has_access())"),
    "check_access_rule": (18, "check_access() (or has_access())"),
    "_filter_access_rules": (18, "_filtered_access()"),
    "_filter_access_rules_python": (18, "_filtered_access()"),
    "_check_recursion": (18, "_has_cycle(), which returns True when there is a cycle"),
    "_check_m2m_recursion": (
        18,
        "_has_cycle(), which returns True when there is a cycle",
    ),
    "toggle_active": (19, "action_archive() or action_unarchive()"),
    "check_field_access_rights": (
        19,
        "_check_field_access(), or fields_get() for the list of allowed fields",
    ),
}

# Overriding these is harmful, not only deprecated: no Odoo 19 code path calls them.
_OVERRIDE_IS_DEAD = {"read_group"}


@rule(
    name="deprecated-orm-api-usage",
    category="Upgrade Safety",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="18.0",
)
def check_deprecated_orm_api_usage(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag calls of ORM methods the running Odoo version still has but deprecates.

    A deprecated method keeps working and logs a warning, so it is lower priority than a
    removed one. A call whose receiver is not obviously a record is reported at medium
    confidence, because the object may be unrelated to the ORM.
    """
    major = odoo_major(odoo_version)
    if major is None or (
        is_test_file(file_path, module_name)
        or is_migration_file(file_path, module_name)
    ):
        return []
    deprecated = {name: v for name, v in _DEPRECATED.items() if major >= v[0]}
    if not deprecated:
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []

    def emit(
        name: str, node: ast.AST, confidence: str, title: str, message: str
    ) -> None:
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="deprecated-orm-api-usage",
                category="Upgrade Safety",
                severity="warning",
                tier="P2",
                source="native",
                confidence=confidence,
                title=title,
                message=message,
                help=f"Use {deprecated[name][1]} instead.",
                odoo_version=odoo_version,
            )
        )

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not is_model_class(cls):
            continue
        for stmt in cls.body:
            if (
                isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                and stmt.name in deprecated
                and stmt.name in _OVERRIDE_IS_DEAD
            ):
                emit(
                    stmt.name,
                    stmt,
                    "high",
                    f"Override of {stmt.name}() is not called by Odoo "
                    f"{deprecated[stmt.name][0]}",
                    f"Odoo {deprecated[stmt.name][0]}.0 deprecated {stmt.name}(): grouped "
                    "views (list, kanban, pivot, graph) go through web_read_group() and "
                    "formatted_read_group(), which use _read_group() and never call it. "
                    "This override only runs for addons that still call read_group() "
                    "themselves.",
                )

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in deprecated
        ):
            continue
        kind = receiver_kind(node.func.value)
        if kind == "super":
            continue
        name = node.func.attr
        since = deprecated[name][0]
        emit(
            name,
            node,
            "high" if kind == "record" else "medium",
            f"{name}() is deprecated since Odoo {since}",
            f"Call to {name}(), which Odoo {since}.0 deprecates. It still works and "
            "logs a deprecation warning; a later release will remove it.",
        )
    return diags
