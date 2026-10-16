# src/odoo_doctor/rules/manifest/data_order_risk.py
"""Rule: manifest-data-order-risk [Module Hygiene, P2]."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules.registry import rule


def _is_security_file(path_str: str) -> bool:
    p = Path(path_str)
    name = p.name
    # A file name that says view/action/menu wins over the directory it sits in:
    # `security/foo_menu.xml` adjusts menu visibility, it does not create groups/ACLs.
    if any(k in name for k in ("view", "action", "menu")):
        return False
    if "security" in p.parts:
        return True
    if "ir.model.access" in name or "security" in name or "groups" in name:
        return True
    return False


def _is_view_action_file(path_str: str) -> bool:
    p = Path(path_str)
    parts = p.parts
    if any(d in parts for d in ("views", "report", "wizard")):
        return True
    name = p.name
    if any(k in name for k in ("view", "action", "menu")):
        return True
    return False


def _read_xml(module_dir: Path, rel: str) -> ET.Element | None:
    if not rel.endswith(".xml"):
        return None
    try:
        return ET.fromstring((module_dir / rel).read_bytes())
    except (OSError, ET.ParseError):
        return None


def _qualify(module_name: str, xml_id: str) -> str:
    return xml_id if "." in xml_id else f"{module_name}.{xml_id}"


def _own_group_definitions(root: ET.Element, module_name: str) -> set[str]:
    """Groups this file creates or updates *in this module*.

    `<record id="base.group_user" model="res.groups">` updates somebody else's group
    and is not a definition.
    """
    out: set[str] = set()
    for el in root.iter("record"):
        if el.get("model") == "res.groups" and el.get("id"):
            qualified = _qualify(module_name, el.get("id", ""))
            if qualified.split(".", 1)[0] == module_name:
                out.add(qualified)
    return out


def _split_groups(value: str, module_name: str) -> set[str]:
    """`"a.g1,!b.g2"` -> {"a.g1", "b.g2"}; unqualified IDs belong to *module_name*."""
    ids = (part.strip().lstrip("!").strip() for part in value.split(","))
    return {_qualify(module_name, i) for i in ids if i}


_REF_CALL = re.compile(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)")
# Record fields that hold groups (`groups` is the many2many of ir.rule).
_GROUP_FIELDS = ("groups_id", "group_ids", "groups")


def _load_time_group_refs(root: ET.Element, module_name: str) -> set[str]:
    """Group XML IDs this file resolves while it is loaded (a missing one raises).

    Sources, odoo/tools/convert.py (17.0 / 19.0): `<menuitem groups=...>` goes through
    `id_get` (325-334 / 318-327); `<field ref=...>` through `id_get` (432 / 426) and
    `ref('...')` in `eval` through the same `id_get` (234 / 229), both raising unless
    `forcecreate="False"`; `<template groups=...>` becomes `ref('...')` in an eval
    (532-535 / 528-530). A group named in a view arch `groups=` is NOT here: Odoo only
    logs a warning (ir_ui_view.py 2923-2926 / 3463-3466).
    """
    refs: set[str] = set()
    for tag in ("menuitem", "template"):
        for el in root.iter(tag):
            refs |= _split_groups(el.get("groups", ""), module_name)
    for el in root.iter("field"):
        if el.get("name") in _GROUP_FIELDS:
            if el.get("ref"):
                refs.add(_qualify(module_name, el.get("ref", "")))
            refs |= {
                _qualify(module_name, m) for m in _REF_CALL.findall(el.get("eval", ""))
            }
    return refs


def _declared_ids(root: ET.Element, module_name: str) -> set[str]:
    out: set[str] = set()
    for el in root.iter():
        xml_id = el.get("id")
        if xml_id:
            out |= {xml_id, _qualify(module_name, xml_id)}
    return out


class Risk(NamedTuple):
    file: str
    index: int  # position of the security file in `data`
    target: (
        int  # position of the first earlier file that already loads one of its groups
    )


def analyze(module_dir: Path, module_name: str, data: list[str]) -> list[Risk]:
    """Security files that create a group an earlier file already needs at load time.

    A group counts as created by the first file that declares it in this module; a later
    file that only re-declares it is an update and is not a risk.
    """
    first_definition: dict[str, int] = {}
    first_loader: dict[str, int] = {}
    created: dict[int, set[str]] = {}
    for idx, rel in enumerate(data):
        root = _read_xml(module_dir, rel)
        if root is None:
            continue
        for group in _own_group_definitions(root, module_name):
            first_definition.setdefault(group, idx)
            if first_definition[group] == idx:
                created.setdefault(idx, set()).add(group)
        for group in _load_time_group_refs(root, module_name):
            first_loader.setdefault(group, idx)
    risks = []
    for idx, groups in sorted(created.items()):
        loaders = [
            first_loader[g]
            for g in groups
            if g in first_loader and first_loader[g] < idx
        ]
        if loaders:
            risks.append(Risk(data[idx], idx, min(loaders)))
    return risks


def risky_security_files(
    module_dir: Path, module_name: str, data: list[str]
) -> tuple[list[str], list[str]]:
    """Security files listed after a view/action file: (`high`, `medium`)."""
    high_files = {r.file for r in analyze(module_dir, module_name, data)}
    high: list[str] = []
    medium: list[str] = []
    seen_view_file = False
    for rel in data:
        if _is_security_file(rel):
            if seen_view_file:
                (high if rel in high_files else medium).append(rel)
        elif _is_view_action_file(rel):
            seen_view_file = True
    return high, medium


def safe_placement(
    module_dir: Path, module_name: str, data: list[str]
) -> dict[str, int] | None:
    """{high file: index of the file to move it in front of}; None when a move cannot be
    shown to keep everything that file mentions loaded before it.

    A file moved in front of its first consumer keeps every earlier file before it; what
    could break is something it depends on that sits between the consumer and its old
    position. So: if the file mentions an XML ID that such an intervening file declares,
    decline (the check is a conservative token match: a false alarm only means "do not fix").
    """
    placement: dict[str, int] = {}
    for risk in analyze(module_dir, module_name, data):
        try:
            text = (module_dir / risk.file).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        mentioned = set(re.findall(r"[A-Za-z_][\w.]*", text))
        for between in data[risk.target : risk.index]:
            root = _read_xml(module_dir, between)
            if root is not None and mentioned & _declared_ids(root, module_name):
                return None
        placement[risk.file] = risk.target
    return placement


@rule(
    name="manifest-data-order-risk",
    category="Module Hygiene",
    tier="P2",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
    fixable=True,
)
def check_data_order_risk(ctx: ModuleContext) -> list[Diagnostic]:
    data = list(ctx.manifest.data)
    first_view_file = next((f for f in data if _is_view_action_file(f)), "")
    high, medium = risky_security_files(ctx.path, ctx.name, data)
    return [
        Diagnostic(
            module=ctx.name,
            file_path=str(ctx.path / "__manifest__.py"),
            line=1,  # Baseline: report line 1
            column=0,
            rule="manifest-data-order-risk",
            category="Module Hygiene",
            severity="error",
            tier="P2",
            source="native",
            confidence="high" if data_file in high else "medium",
            title="Security file loaded after views/actions",
            message=f"Security file '{data_file}' is loaded after view/action file '{first_view_file}'.",
            help="Move security files before views and actions in the 'data' list to ensure access rights are created first.",
            odoo_version=ctx.odoo_version,
        )
        for data_file in data
        if data_file in high or data_file in medium
    ]
