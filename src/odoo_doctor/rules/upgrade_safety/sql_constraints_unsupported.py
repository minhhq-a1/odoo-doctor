# src/odoo_doctor/rules/upgrade_safety/sql_constraints_unsupported.py
"""Rule: sql-constraints-unsupported [Upgrade Safety, P1]."""

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


def _constraint_names(value: ast.expr | None) -> list[str]:
    """Names of the ``(name, definition, message)`` tuples of a literal list."""
    if not isinstance(value, (ast.List, ast.Tuple)):
        return []
    names = []
    for item in value.elts:
        if (
            isinstance(item, (ast.Tuple, ast.List))
            and item.elts
            and isinstance(item.elts[0], ast.Constant)
            and isinstance(item.elts[0].value, str)
        ):
            names.append(item.elts[0].value)
    return names


@rule(
    name="sql-constraints-unsupported",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="19.0",
)
def check_sql_constraints_unsupported(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag a model's ``_sql_constraints`` list, which Odoo 19 no longer reads.

    Odoo 19 only logs a warning for the attribute and creates none of the constraints,
    so a UNIQUE or CHECK the model relied on silently stops being enforced.
    """
    if is_test_file(file_path, module_name) or is_migration_file(
        file_path, module_name
    ):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not is_model_class(cls):
            continue
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            elif isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
            else:
                continue
            if not any(
                isinstance(t, ast.Name) and t.id == "_sql_constraints" for t in targets
            ):
                continue
            value = stmt.value
            if isinstance(value, (ast.List, ast.Tuple)) and not value.elts:
                continue  # an empty list constrains nothing
            names = _constraint_names(value)
            listed = f" ({', '.join(names)})" if names else ""
            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=str(file_path),
                    line=stmt.lineno,
                    column=stmt.col_offset,
                    rule="sql-constraints-unsupported",
                    category="Upgrade Safety",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="high",
                    title=f"_sql_constraints is ignored on Odoo 19 in {cls.name}",
                    message=(
                        f"Class {cls.name} sets _sql_constraints{listed}. Odoo 19 no "
                        "longer reads this attribute (it only logs a warning), so none "
                        "of these constraints is created and nothing enforces them."
                    ),
                    help=(
                        "Declare each constraint as a class attribute: "
                        "_name_uniq = models.Constraint('UNIQUE(name)', 'Name must be "
                        "unique'). Check the database for duplicates before adding a "
                        "UNIQUE one."
                    ),
                    odoo_version=odoo_version,
                )
            )
    return diags
