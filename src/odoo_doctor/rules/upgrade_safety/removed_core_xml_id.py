# src/odoo_doctor/rules/upgrade_safety/removed_core_xml_id.py
"""Rule: removed-core-xml-id [Upgrade Safety, P1]."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules._module_files import python_files
from odoo_doctor.rules.registry import rule
from odoo_doctor.rules.upgrade_safety._core_refs import classify

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Ids Odoo creates from its registries at runtime: no data file declares them.
_DYNAMIC_PREFIXES = ("model_", "field_", "module_")


def _env_ref_calls(tree: ast.AST) -> Iterator[tuple[ast.Call, bool]]:
    """``env.ref("lit")`` calls that raise when the id is missing, and whether a ``try`` guards them."""

    def walk(node: ast.AST, guarded: bool) -> Iterator[tuple[ast.Call, bool]]:
        if isinstance(node, ast.Call) and _is_env_ref(node):
            yield node, guarded
        for field_name, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            # a try body is guarded; its handlers, else and finally are not
            inside = guarded or (isinstance(node, ast.Try) and field_name == "body")
            for child in children:
                if isinstance(child, ast.AST):
                    yield from walk(child, inside)

    yield from walk(tree, False)


def _is_env_ref(call: ast.Call) -> bool:
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "ref"):
        return False
    owner = func.value
    named_env = (isinstance(owner, ast.Name) and owner.id == "env") or (
        isinstance(owner, ast.Attribute) and owner.attr == "env"
    )
    if not (named_env and call.args):
        return False
    arg = call.args[0]
    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        return False
    return not any(
        kw.arg == "raise_if_not_found"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is False
        for kw in call.keywords
    )


def _references(ctx: ModuleContext) -> Iterator[tuple[str, str, int, bool]]:
    """``(xml id, file, line, guarded)`` of every literal reference to an id of another module."""
    for info in ctx.xml_records:
        for ref in info.refs:
            yield ref, info.file_path, info.ref_lines.get(ref, info.line), False
    for view in ctx.views:
        if view.inherit_id:
            yield view.inherit_id, view.file_path, view.line, False
    for path in python_files(ctx):
        tree = parse_python(path)
        if tree is None:
            continue
        for call, guarded in _env_ref_calls(tree):
            yield call.args[0].value, str(path), call.lineno, guarded  # type: ignore[attr-defined]


@rule(
    name="removed-core-xml-id",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="18.0",
)
def check_removed_core_xml_id(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag references to core XML ids that an older Odoo had and this one lacks."""
    diags: list[Diagnostic] = []
    seen: set[tuple[str, str, int]] = set()
    for ref, file_path, line, guarded in _references(ctx):
        module, dot, name = ref.partition(".")
        if not dot or name.startswith(_DYNAMIC_PREFIXES) or module == ctx.name:
            continue
        key = (ref, file_path, line)
        if key in seen:
            continue
        seen.add(key)
        if ctx.resolver.resolve_xml_id(ref).status == ResolveResult.FOUND:
            continue  # declared by a scanned addon (possibly in the core's namespace)
        verdict = classify(ctx, module, lambda i, m=module, n=name: i.has_xml_id(m, n))
        if verdict is None:
            continue
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=file_path,
                line=line,
                column=0,
                rule="removed-core-xml-id",
                category="Upgrade Safety",
                severity="error",
                tier="P1",
                source="native",
                confidence="medium" if guarded else verdict.confidence,
                title=f"Core XML id removed: {ref}",
                message=(
                    f"'{ref}' is declared by core Odoo {', '.join(verdict.seen_in)} "
                    f"but not by {verdict.target}; loading or upgrading the module "
                    "fails on this reference."
                ),
                help="Use the id that replaced it in the new Odoo, or declare it in your module.",
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
