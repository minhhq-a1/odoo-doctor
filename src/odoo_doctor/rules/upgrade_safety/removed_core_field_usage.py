# src/odoo_doctor/rules/upgrade_safety/removed_core_field_usage.py
"""Rule: removed-core-field-usage [Upgrade Safety, P1]."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import odoo_major
from odoo_doctor.rules._module_files import (
    data_files,
    elements,
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

_GROUPS = (19, "group_ids")

# model -> {field: (first Odoo major without it, what to use instead)}. Only fields that
# the ORM source of that release no longer defines on the model belong here.
_REMOVED_FIELDS: dict[str, dict[str, tuple[int, str]]] = {
    "res.users": {"groups_id": _GROUPS},
    "ir.ui.view": {"groups_id": _GROUPS},
    "ir.ui.menu": {"groups_id": _GROUPS},
    "ir.actions.act_window": {"groups_id": _GROUPS},
    "ir.actions.server": {"groups_id": _GROUPS},
    "ir.actions.report": {"groups_id": _GROUPS},
    "res.groups": {
        "category_id": (
            19,
            "privilege_id, a res.groups.privilege record that carries the category",
        ),
        "users": (19, "user_ids"),
    },
    "product.template": {
        "detailed_type": (18, "type ('consu', 'service', 'combo') plus is_storable")
    },
    "product.product": {
        "detailed_type": (18, "type ('consu', 'service', 'combo') plus is_storable")
    },
    "res.partner": {"mobile": (19, "phone, which now holds both numbers")},
    "crm.lead": {"mobile": (19, "phone, which now holds both numbers")},
    "account.account": {
        "deprecated": (19, "active (inverted: deprecated=False is active=True)")
    },
    "ir.filters": {
        "user_id": (
            19,
            "user_ids, a many2many: an empty list shares the filter with everyone",
        )
    },
}

# Field names that exist on no other core model, so a Python string or attribute with
# the name is a reference to the removed field. Medium confidence: the object is unknown.
_PYTHON_NAMES = {
    "groups_id": (19, "group_ids"),
    "detailed_type": (18, "type plus is_storable"),
}


def _removed(model: str, field: str, major: int) -> tuple[int, str] | None:
    entry = _REMOVED_FIELDS.get(model, {}).get(field)
    return entry if entry is not None and major >= entry[0] else None


def _own_model_fields(tree: ast.AST) -> set[str]:
    """Names a class defines as fields of a model it creates (``_name``, no ``_inherit``)."""
    own: set[str] = set()
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        assigned = {
            t.id
            for st in cls.body
            if isinstance(st, ast.Assign)
            for t in st.targets
            if isinstance(t, ast.Name)
        }
        if "_name" in assigned and "_inherit" not in assigned:
            own |= assigned
    return own


def _is_compat_guard(parent: ast.AST | None, node: ast.Constant) -> bool:
    """``'groups_id' in rec._fields`` and ``hasattr(rec, 'groups_id')``: version probes."""
    if isinstance(parent, ast.Compare) and any(
        isinstance(op, (ast.In, ast.NotIn)) for op in parent.ops
    ):
        return True
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id in ("hasattr", "getattr")
    )


def _inside_probe(node: ast.AST, parents: dict, name: str) -> bool:
    """True inside an ``if`` whose test mentions the quoted name (a version probe).

    ``if 'groups_id' in user._fields: return user.groups_id`` is a compatibility branch
    that only runs on the version that still has the field.
    """
    quoted = (f"'{name}'", f'"{name}"')
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.If) and any(
            q in ast.unparse(current.test) for q in quoted
        ):
            return True
        current = parents.get(current)
    return False


@rule(
    name="removed-core-field-usage",
    category="Upgrade Safety",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="18.0",
)
def check_removed_core_field_usage(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag fields of core models that the running Odoo version no longer has.

    In data files the model is known from the ``<record model=...>`` (and from the model
    of an ``ir.ui.view``), so a removed field is reported at high confidence: the record
    fails to load. In Python only names that no other core model uses are looked for
    (``groups_id``, ``detailed_type``), at medium confidence.
    """
    major = odoo_major(ctx.odoo_version)
    if major is None:
        return []
    diags: list[Diagnostic] = []

    def emit(path, line, model, field, since, instead, confidence="high") -> None:
        diags.append(
            make_diag(
                ctx=ctx,
                path=path,
                line=line,
                rule="removed-core-field-usage",
                category="Upgrade Safety",
                tier="P1",
                severity="error",
                confidence=confidence,
                title=f"'{field}' no longer exists on {model} (Odoo {since})",
                message=(
                    f"'{field}' was removed from {model} in Odoo {since}.0. A record "
                    "that sets it, or a view that shows it, fails to load."
                    if confidence == "high"
                    else f"'{field}' was removed from the core models that had it in "
                    f"Odoo {since}.0. This reference raises an error or matches nothing."
                ),
                help=f"Use {instead} instead.",
            )
        )

    for path in data_files(ctx):
        tree = parse_xml(path)
        if tree is None:
            continue
        for model in _REMOVED_FIELDS:
            for record in records(tree, model):
                for f in record.findall("field"):
                    entry = _removed(model, f.get("name", ""), major)
                    if entry:
                        emit(path, line_of(f, record), model, f.get("name"), *entry)
        for record, arch in view_arches(tree):
            model_field = next(
                (f for f in record.findall("field") if f.get("name") == "model"), None
            )
            model = (model_field.text or "").strip() if model_field is not None else ""
            if model not in _REMOVED_FIELDS:
                continue
            for el in elements(arch):
                if el.tag == "field" and not any(
                    p.tag == "field" for p in el.iterancestors() if p is not arch
                ):
                    entry = _removed(model, el.get("name", ""), major)
                    if entry:
                        emit(path, line_of(el, record), model, el.get("name"), *entry)
                elif el.tag == "xpath":
                    for name in _REMOVED_FIELDS[model]:
                        entry = _removed(model, name, major)
                        if entry and re.search(
                            rf"@name\s*=\s*['\"]{re.escape(name)}['\"]",
                            el.get("expr", ""),
                        ):
                            emit(path, line_of(el, record), model, name, *entry)

    names = {n: v for n, v in _PYTHON_NAMES.items() if major >= v[0]}
    if not names:
        return diags
    parsed = [(p, parse_python(p)) for p in python_files(ctx)]
    own = set()
    for _, tree in parsed:
        if tree is not None:
            own |= _own_model_fields(tree)
    wanted = {n: v for n, v in names.items() if n not in own}
    if not wanted:
        return diags
    for path, tree in parsed:
        if tree is None:
            continue
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Attribute) and node.attr in wanted:
                name = node.attr
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in wanted
                and not _is_compat_guard(parents.get(node), node)
            ):
                name = node.value
                if isinstance(parents.get(node), ast.Expr):
                    continue  # a bare string statement: a docstring
            if name is None or _inside_probe(node, parents, name):
                continue
            since, instead = wanted[name]
            emit(path, node.lineno, "the core models", name, since, instead, "medium")
    return diags
