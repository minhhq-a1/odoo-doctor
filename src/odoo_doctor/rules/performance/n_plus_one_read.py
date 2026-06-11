# src/odoo_doctor/rules/performance/n_plus_one_read.py
"""Rule: n-plus-one-read [Performance, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules.registry import rule


def _chain_depth(node: ast.Attribute) -> int:
    """Count chained attribute hops: a.b.c -> 2."""
    depth = 0
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        depth += 1
        cur = cur.value
    return depth


@rule(
    name="n-plus-one-read",
    category="Performance",
    tier="P1",
    severity="warning",
    default_confidence="low",
    needs_context=False,
    min_version="14.0",
)
def check_n_plus_one_read(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    diags: list[Diagnostic] = []
    for loop in (n for n in ast.walk(tree) if isinstance(n, ast.For)):
        # The loop variable name(s).
        loop_vars: set[str] = set()
        if isinstance(loop.target, ast.Name):
            loop_vars.add(loop.target.id)
        if not loop_vars:
            continue
        seen_lines: set[int] = set()
        for node in ast.walk(loop):
            if not isinstance(node, ast.Attribute):
                continue
            # Chain depth >= 2 means at least loop_var.rel.attr
            if _chain_depth(node) < 2:
                continue
            # Find the root Name of the chain.
            root: ast.expr = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if not (isinstance(root, ast.Name) and root.id in loop_vars):
                continue
            if node.lineno in seen_lines:
                continue
            seen_lines.add(node.lineno)
            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=str(file_path),
                    line=node.lineno,
                    column=node.col_offset,
                    rule="n-plus-one-read",
                    category="Performance",
                    severity="warning",
                    tier="P1",
                    source="native",
                    confidence="low",
                    title="Possible N+1 relational read in loop",
                    message=(
                        f"Chained attribute access on loop variable at line "
                        f"{node.lineno} may trigger one query per iteration."
                    ),
                    help=(
                        "Prefetch related records before the loop (e.g. "
                        "mapped()) or read the needed fields in one batch."
                    ),
                    odoo_version=odoo_version,
                )
            )
    return diags
