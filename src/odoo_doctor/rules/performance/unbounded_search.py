# src/odoo_doctor/rules/performance/unbounded_search.py
"""Rule: unbounded-search [Performance, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.source import read_source
from odoo_doctor.rules._ast_helpers import receiver_is_orm
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule


@rule(
    name="unbounded-search",
    category="Performance",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_unbounded_search(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_risky_context(node):
            _check_function_body(node, diags, file_path, module_name, odoo_version)

    return diags


def _is_risky_context(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # Check compute naming or cron naming
    name = func.name
    if (
        name.startswith("_compute_")
        or name.startswith("_cron")
        or name.startswith("cron_")
    ):
        return True

    # Check decorators for @api.depends or @http.route
    for dec in func.decorator_list:
        dec_name = None
        if isinstance(dec, ast.Name):
            dec_name = dec.id
        elif isinstance(dec, ast.Attribute):
            dec_name = dec.attr
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                dec_name = dec.func.id
            elif isinstance(dec.func, ast.Attribute):
                dec_name = dec.func.attr

        if dec_name in ("depends", "route"):
            return True

    return False


def _check_function_body(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
) -> None:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("search", "search_read"):
            continue

        if not receiver_is_orm(node):
            continue

        # Check for empty list as first positional argument
        has_empty_domain = False
        if (
            node.args
            and isinstance(node.args[0], ast.List)
            and len(node.args[0].elts) == 0
        ):
            has_empty_domain = True

        # If empty domain is provided via keyword arg "domain"
        for kw in node.keywords:
            if (
                kw.arg == "domain"
                and isinstance(kw.value, ast.List)
                and len(kw.value.elts) == 0
            ):
                has_empty_domain = True

        if not has_empty_domain:
            continue

        # Check for presence of 'limit' keyword argument
        has_limit = any(kw.arg == "limit" for kw in node.keywords)
        if has_limit:
            continue

        diags.append(
            Diagnostic(
                module=module,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="unbounded-search",
                category="Performance",
                severity="warning",
                tier="P2",
                source="native",
                confidence="high",
                title=f"Unbounded '{node.func.attr}' in risky context",
                message=f"'{node.func.attr}()' at line {node.lineno} has an empty domain and no limit in a risky context.",
                help="Add a 'limit' or restrict the search domain to prevent full table scans and memory exhaustion.",
                odoo_version=version,
            )
        )
