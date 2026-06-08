# src/odoo_doctor/rules/correctness/compute_missing_depends.py
"""Rule: compute-missing-depends [Correctness, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.core.source import read_source
from odoo_doctor.graph.resolver import ResolveResult

# Standard ORM fields and methods that shouldn't trigger "missing depends"
_MAGIC_FIELDS = {
    "id",
    "env",
    "display_name",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
}


@rule(
    name="compute-missing-depends",
    category="Correctness",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_compute_missing_depends(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for model_name, model in ctx.models.items():
        if not model.file_path:
            continue

        source = read_source(Path(model.file_path))
        if not source:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for method_name, method in model.methods.items():
            if "api.depends" not in method.decorators or not method.depends:
                continue

            # Build cover set (first segment of depends)
            cover_set = set()
            for dep in method.depends:
                cover_set.add(dep.split(".")[0])

            # Find the function def in the AST
            func_node = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == method_name and node.lineno == method.line:
                        func_node = node
                        break

            if not func_node:
                continue

            # Find all `self.<attr>` reads inside the method
            reads = _find_self_attribute_reads(func_node)

            for attr in reads:
                if attr in cover_set or attr in _MAGIC_FIELDS:
                    continue

                # Resolve the field
                lookup = ctx.resolver.resolve_field(model_name, attr)
                if lookup.status == ResolveResult.FOUND:
                    diags.append(
                        Diagnostic(
                            module=ctx.name,
                            file_path=model.file_path,
                            line=method.line,
                            column=0,
                            rule="compute-missing-depends",
                            category="Correctness",
                            severity="warning",
                            tier="P2",
                            source="native",
                            confidence="high",
                            title=f"Compute reads undeclared field '{attr}'",
                            message=f"Compute method '{method_name}' reads field '{attr}' but it is not declared in @api.depends.",
                            help=f"Add '{attr}' to the @api.depends decorator to ensure the compute triggers correctly.",
                            odoo_version=ctx.odoo_version,
                        )
                    )

    return diags


def _find_self_attribute_reads(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    reads = set()
    self_aliases = {"self"}
    for node in ast.walk(func):
        if isinstance(node, ast.For):
            if isinstance(node.iter, ast.Name) and node.iter.id in self_aliases:
                if isinstance(node.target, ast.Name):
                    self_aliases.add(node.target.id)

    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if isinstance(node.value, ast.Name) and node.value.id in self_aliases:
                reads.add(node.attr)
    return reads
