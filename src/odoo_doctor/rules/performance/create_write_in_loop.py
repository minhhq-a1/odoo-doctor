# src/odoo_doctor/rules/performance/create_write_in_loop.py
"""Rules: create-in-loop, write-in-loop [Performance, P1]."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file, orm_calls_in_loops
from odoo_doctor.rules.registry import rule


def _loop_diagnostics(
    file_path: Path,
    module: str,
    version: str,
    method_name: str,
    rule_name: str,
) -> list[Diagnostic]:
    if is_test_file(file_path, module):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []
    return [
        Diagnostic(
            module=module,
            file_path=str(file_path),
            line=node.lineno,
            column=node.col_offset,
            rule=rule_name,
            category="Performance",
            severity="error",
            tier="P1",
            source="native",
            confidence="medium" if guessed else "high",
            title=f"ORM '{method_name}' called inside loop",
            message=f"'{method_name}()' at line {node.lineno} is called inside a loop. Consider batching.",
            help=f"Move the '{method_name}()' call outside the loop and batch the operation.",
            odoo_version=version,
        )
        for node, _loop, guessed in orm_calls_in_loops(tree, {method_name})
    ]


def check_create_write_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Helper used by tests to get both."""
    return check_create_in_loop(
        file_path, module_name, odoo_version
    ) + check_write_in_loop(file_path, module_name, odoo_version)


@rule(
    name="create-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_create_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    return _loop_diagnostics(
        file_path, module_name, odoo_version, "create", "create-in-loop"
    )


@rule(
    name="write-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_write_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    return _loop_diagnostics(
        file_path, module_name, odoo_version, "write", "write-in-loop"
    )
