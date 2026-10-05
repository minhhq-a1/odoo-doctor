# src/odoo_doctor/rules/correctness/hardcoded_company_or_currency.py
"""Rule: hardcoded-company-or-currency [Correctness, P2]."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule

_MAIN_COMPANY = "base.main_company"
_CURRENCY_XML_ID = re.compile(r"^base\.[A-Z]{3}$")


@rule(
    name="hardcoded-company-or-currency",
    category="Correctness",
    tier="P2",
    severity="warning",
    default_confidence="medium",
    needs_context=False,
    min_version="14.0",
)
def check_hardcoded_company_or_currency(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag `env.ref('base.main_company')` / `env.ref('base.USD')` in business code."""
    path = Path(file_path)
    if is_test_file(path, module_name) or "migrations" in path.parts:
        return []
    if path.name == "hooks.py":
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    visitor = _Visitor(file_path, module_name, odoo_version)
    visitor.visit(tree)
    return visitor.diagnostics


class _Visitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, module_name: str, odoo_version: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.odoo_version = odoo_version
        self.diagnostics: list[Diagnostic] = []
        self._functions: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        # Install hooks run once at (un)install and may legitimately name the main
        # company or a currency.
        if any(name.endswith("_hook") for name in self._functions):
            return
        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "ref"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return
        xml_id = node.args[0].value
        if xml_id == _MAIN_COMPANY:
            what = "the main company"
            fix = "Use self.env.company (or the record's own company_id)."
        elif _CURRENCY_XML_ID.match(xml_id):
            what = f"the currency {xml_id.split('.', 1)[1]}"
            fix = (
                "Use the company currency (self.env.company.currency_id) or the "
                "document's currency_id."
            )
        else:
            return
        self.diagnostics.append(
            Diagnostic(
                module=self.module_name,
                file_path=str(self.file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="hardcoded-company-or-currency",
                category="Correctness",
                severity="warning",
                tier="P2",
                source="native",
                confidence="medium",
                title=f"Hardcoded reference to {what}",
                message=(
                    f"'{xml_id}' hardcodes {what}; in a multi-company or "
                    "multi-currency database this picks the wrong record."
                ),
                help=fix,
                odoo_version=self.odoo_version,
            )
        )
