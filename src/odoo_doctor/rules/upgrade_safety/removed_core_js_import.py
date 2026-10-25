# src/odoo_doctor/rules/upgrade_safety/removed_core_js_import.py
"""Rule: removed-core-js-import [Upgrade Safety, P1]."""

from __future__ import annotations

import posixpath
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.graph.core_index import get_core_index
from odoo_doctor.rules.registry import rule
from odoo_doctor.rules.upgrade_safety._core_refs import classify, relocation_hint
from odoo_doctor.rules.upgrade_safety._js_imports import (
    js_imports,
    module_js_files,
    specifier_target,
)

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="removed-core-js-import",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="18.0",
)
def check_removed_core_js_import(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag `@module/path` imports of core JS files that an older Odoo had and this one lacks."""
    diags: list[Diagnostic] = []
    for path in module_js_files(ctx):
        text = read_source(path, ctx.path)
        if text is None:
            continue
        for imp in js_imports(text):
            target = specifier_target(imp.specifier)
            if target is None:
                continue
            module, rel = target
            verdict = classify(
                ctx, module, lambda i, m=module, r=rel: i.has_static(m, r)
            )
            if verdict is None:
                continue
            hint = relocation_hint(
                get_core_index(ctx.odoo_version), posixpath.basename(rel)
            )
            diags.append(
                Diagnostic(
                    module=ctx.name,
                    file_path=str(path),
                    line=imp.line,
                    column=0,
                    rule="removed-core-js-import",
                    category="Upgrade Safety",
                    severity="error",
                    tier="P1",
                    source="native",
                    confidence="medium" if imp.dynamic else verdict.confidence,
                    title=f"Core JS module removed: {imp.specifier}",
                    message=(
                        f"'{imp.specifier}' is a core file of Odoo "
                        f"{', '.join(verdict.seen_in)} that is not in "
                        f"{verdict.target}; the bundle fails to load it."
                    ),
                    help=(
                        "Import the file's replacement from the new Odoo, or copy the code "
                        f"into your module.{hint}"
                    ),
                    odoo_version=ctx.odoo_version,
                )
            )
    return diags
