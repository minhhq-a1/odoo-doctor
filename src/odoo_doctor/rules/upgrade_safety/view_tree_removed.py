# src/odoo_doctor/rules/upgrade_safety/view_tree_removed.py
"""Rule: view-tree-removed [Upgrade Safety, P1]."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._module_files import (
    data_files,
    elements,
    field_of,
    field_text,
    line_of,
    make_diag,
    parse_xml,
    python_files,
    records,
    view_arches,
)
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_TREE_MODE = re.compile(r"(?:^|,)\s*tree\s*(?:,|$)")
_EVAL_VIEW_MODE = re.compile(r"""['"]view_mode['"]\s*:\s*['"]([^'"]*)['"]""")
_PREDICATES = re.compile(r"\[[^\]]*\]")


def _has_tree_mode(value: str) -> bool:
    return bool(_TREE_MODE.search(value))


def _xpath_names_tree(expr: str) -> bool:
    steps = _PREDICATES.sub("", expr).split("/")
    return any(step.strip() == "tree" for step in steps)


def _eval_has_tree_mode(text: str) -> bool:
    return any(_has_tree_mode(m) for m in _EVAL_VIEW_MODE.findall(text or ""))


def _py_action_dicts(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {
                k.value: v
                for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            yield node, keys


def _looks_like_action(keys: dict) -> bool:
    if "res_model" in keys:
        return True
    action_type = keys.get("type")
    return isinstance(action_type, ast.Constant) and action_type.value in (
        "ir.actions.act_window",
    )


@rule(
    name="view-tree-removed",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="18.0",
)
def check_view_tree_removed(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag the ``tree`` view type, which Odoo 18 renamed to ``list``.

    The architecture ``<tree>``, the ``tree`` view mode of an action and the ``tree`` step
    of an XPath no longer match anything: Odoo 18 and later have no ``tree`` view type, so
    the view is rejected or the action cannot open.
    """
    diags: list[Diagnostic] = []

    def emit(path, line, title, message, confidence="high") -> None:
        diags.append(
            make_diag(
                ctx=ctx,
                path=path,
                line=line,
                rule="view-tree-removed",
                category="Upgrade Safety",
                tier="P1",
                severity="error",
                confidence=confidence,
                title=title,
                message=message,
                help=(
                    "Rename the view type: <tree> becomes <list>, view_mode 'tree,form' "
                    "becomes 'list,form', and an XPath step tree becomes list. A nested "
                    "tree inside an x2many field becomes <list> as well."
                ),
            )
        )

    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for record, arch in view_arches(tree):
            trees = [e for e in elements(arch) if e.tag == "tree"]
            xpaths = [
                e
                for e in elements(arch)
                if e.tag == "xpath" and _xpath_names_tree(e.get("expr", ""))
            ]
            is_tree_type = field_text(record, "type") == "tree"
            found = trees + xpaths
            if not found and not is_tree_type:
                continue
            what = []
            if trees:
                what.append(f"{len(trees)} <tree> element(s)")
            if xpaths:
                what.append(f"{len(xpaths)} XPath step(s) named tree")
            if is_tree_type:
                what.append("type tree")
            rec_id = record.get("id", "<anonymous>")
            emit(
                path,
                line_of(*(found[:1]), field_of(record, "type"), record),
                f"View '{rec_id}' still uses the tree view type",
                f"View '{rec_id}' has {', '.join(what)}. Odoo 18 renamed the tree view "
                "type to list, so the view is rejected on install or update.",
            )
        for record in records(tree, "ir.actions.act_window"):
            mode = field_text(record, "view_mode")
            via_eval = any(
                _eval_has_tree_mode(f.get("eval", "")) for f in record.findall("field")
            )
            if _has_tree_mode(mode) or via_eval:
                rec_id = record.get("id", "<anonymous>")
                emit(
                    path,
                    line_of(field_of(record, "view_mode"), record),
                    f"Action '{rec_id}' opens the tree view mode",
                    f"Action '{rec_id}' lists the tree view mode. Odoo 18 has no tree "
                    "view type, only list.",
                )
        for record in records(tree, "ir.actions.act_window.view"):
            if field_text(record, "view_mode") == "tree" or any(
                _eval_has_tree_mode(f.get("eval", "")) for f in record.findall("field")
            ):
                rec_id = record.get("id", "<anonymous>")
                emit(
                    path,
                    line_of(field_of(record, "view_mode"), record),
                    f"Action view '{rec_id}' uses the tree view mode",
                    f"Action view '{rec_id}' has view_mode tree. Odoo 18 renamed it to list.",
                )

    for path in python_files(ctx):
        py = parse_python(path)
        if py is None:
            continue
        for node, keys in _py_action_dicts(py):
            confidence = "high" if _looks_like_action(keys) else "medium"
            mode = keys.get("view_mode")
            if (
                isinstance(mode, ast.Constant)
                and isinstance(mode.value, str)
                and _has_tree_mode(mode.value)
            ):
                emit(
                    path,
                    node.lineno,
                    "Action dict uses the tree view mode",
                    "This action dict sets view_mode with tree. Odoo 18 renamed the view "
                    "type to list, so the client cannot open the action.",
                    confidence,
                )
            views = keys.get("views")
            if isinstance(views, (ast.List, ast.Tuple)) and any(
                isinstance(pair, (ast.Tuple, ast.List))
                and len(pair.elts) == 2
                and isinstance(pair.elts[1], ast.Constant)
                and pair.elts[1].value == "tree"
                for pair in views.elts
            ):
                emit(
                    path,
                    node.lineno,
                    "Action dict lists a tree view",
                    "This action dict lists a (view id, 'tree') pair in 'views'. Odoo 18 "
                    "renamed the view type to list.",
                    confidence,
                )
    return diags
