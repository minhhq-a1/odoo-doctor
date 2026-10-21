# src/odoo_doctor/rules/upgrade_safety/fixers.py
"""Fixers for the mechanical Upgrade Safety findings (``fix --upgrade-to``).

Each fixer edits the text of one ``<record>`` (XML) or one action dict (Python) and
nothing else, so comments, indentation and line endings stay as they were. A finding
covers a whole record, so a fixer repairs every occurrence in it. It re-derives the
offenders from the text (never from the finding's wording) and returns None when it
cannot finish the job, so a finding labelled mechanical is either fixed or reported.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import default_fixers
from odoo_doctor.core.upgrade import (
    MECHANICAL_RENAMES,
    is_mechanical,
    parse_field_title,
)
from odoo_doctor.rules.upgrade_safety import _xml_text as xt
from odoo_doctor.rules.upgrade_safety.chatter_div_removed import is_plain_chatter_div
from odoo_doctor.rules.upgrade_safety.search_view_group_attributes import (
    _REJECTED,
    _search_groups,
)
from odoo_doctor.rules.upgrade_safety.view_tree_removed import (
    _EVAL_VIEW_MODE,
    _PREDICATES,
    _TREE_MODE,
    _looks_like_action,
    _py_action_dicts,
    _xpath_names_tree,
)

Edit = tuple[int, int, str]  # [start, end) of the text, replacement


def _apply(text: str, edits: list[Edit]) -> str:
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def _parse(fragment: str) -> etree._Element | None:
    try:
        return etree.fromstring(
            fragment.encode("utf-8"),
            etree.XMLParser(resolve_entities=False, no_network=True),
        )
    except (etree.XMLSyntaxError, ValueError):
        return None


def _tag_of(
    fragment: str, root: etree._Element, element: etree._Element
) -> xt.Tag | None:
    """The start tag in *fragment* of *element* (same position among tags of its name)."""
    same = list(root.iter(element.tag))
    found = xt.start_tags(fragment, element.tag)
    if len(same) != len(found):
        return None  # the text and the parsed tree disagree: do not guess
    return found[same.index(element)]


def _set_attr(fragment: str, tag: xt.Tag, attr: str, rewrite) -> Edit | None:
    """Edit replacing *attr* of *tag* by ``rewrite(raw value)``; None if there is no such attribute."""
    tag_text = fragment[tag.start : tag.end]
    raw = xt.get_attr(tag_text, attr)
    if raw is None:
        return None
    return tag.start, tag.end, xt.set_attr_value(tag_text, attr, rewrite(raw))


def _record(text: str, line: int) -> tuple[int, str, etree._Element] | None:
    span = xt.record_span(text, line)
    if span is None:
        return None
    fragment = text[span[0] : span[1]]
    root = _parse(fragment)
    return None if root is None else (span[0], fragment, root)


def _field(root: etree._Element, name: str) -> etree._Element | None:
    return next((f for f in root.findall("field") if f.get("name") == name), None)


# --- view-tree-removed -----------------------------------------------------------------

_TREE_STEP = re.compile(r"(?<![^/\s])tree(?![^/\s])")
_MODE_TOKEN = re.compile(r"(^|,)(\s*)tree(\s*)(?=,|$)")


def _rename_tree_mode(value: str) -> str:
    return _MODE_TOKEN.sub(r"\1\2list\3", value)


def _rename_xpath_steps(expr: str) -> str:
    """``tree`` steps become ``list``; text inside ``[…]`` predicates is left alone."""
    parts = re.split(f"({_PREDICATES.pattern})", expr)
    return "".join(
        p if i % 2 else _TREE_STEP.sub("list", p) for i, p in enumerate(parts)
    )


def _rename_eval_view_mode(value: str) -> str:
    return _EVAL_VIEW_MODE.sub(
        lambda m: m.group(0).replace(m.group(1), _rename_tree_mode(m.group(1)), 1),
        value,
    )


def _tree_edits_view(fragment: str, root: etree._Element) -> list[Edit] | None:
    arch = _field(root, "arch")
    if arch is None:
        return []
    edits: list[Edit] = []
    for el in arch.iter("tree"):
        tag = _tag_of(fragment, root, el)
        if tag is None:
            return None
        edits.append((tag.start + 1, tag.start + 1 + len("tree"), "list"))
        closing = xt.end_tag_for(fragment, tag)
        if closing is not None:
            edits.append((closing.start + 2, closing.start + 2 + len("tree"), "list"))
    for el in arch.iter("xpath"):
        expr = el.get("expr", "")
        if not _xpath_names_tree(expr):
            continue
        tag = _tag_of(fragment, root, el)
        edit = tag and _set_attr(fragment, tag, "expr", _rename_xpath_steps)
        if not edit:
            return None
        edits.append(edit)
    type_field = _field(root, "type")
    if type_field is not None and (type_field.text or "").strip() == "tree":
        edits += _replace_field_text(
            fragment, root, type_field, lambda s: s.replace("tree", "list")
        )
    return edits


def _replace_field_text(fragment, root, element, rewrite) -> list[Edit]:
    """Rewrite the text of a field that only holds text (whitespace around it is kept)."""
    tag = _tag_of(fragment, root, element)
    closing = xt.end_tag_for(fragment, tag) if tag else None
    if tag is None or closing is None or len(element):
        return []
    return [(tag.end, closing.start, rewrite(fragment[tag.end : closing.start]))]


def _tree_edits_action(fragment: str, root: etree._Element, model: str) -> list[Edit]:
    edits: list[Edit] = []
    mode = _field(root, "view_mode")
    if mode is not None and (
        _TREE_MODE.search(mode.text or "")
        if model == "ir.actions.act_window"
        else (mode.text or "").strip() == "tree"
    ):
        edits += _replace_field_text(fragment, root, mode, _rename_tree_mode)
    for el in root.findall("field"):
        if "tree" not in el.get("eval", ""):
            continue
        tag = _tag_of(fragment, root, el)
        edit = tag and _set_attr(fragment, tag, "eval", _rename_eval_view_mode)
        if edit and edit[2] != fragment[edit[0] : edit[1]]:
            edits.append(edit)
    return edits


def _still_has_tree(root: etree._Element, model: str) -> bool:
    if model == "ir.ui.view":
        arch = _field(root, "arch")
        type_field = _field(root, "type")
        return bool(
            arch is not None
            and (
                next(arch.iter("tree"), None) is not None
                or any(_xpath_names_tree(x.get("expr", "")) for x in arch.iter("xpath"))
            )
            or type_field is not None
            and (type_field.text or "").strip() == "tree"
        )
    mode = _field(root, "view_mode")
    text = (mode.text or "") if mode is not None else ""
    return bool(
        _TREE_MODE.search(text)
        if model == "ir.actions.act_window"
        else text.strip() == "tree"
    ) or any(
        _TREE_MODE.search("".join(_EVAL_VIEW_MODE.findall(f.get("eval", ""))))
        for f in root.findall("field")
    )


def _fix_tree_xml(diag: Diagnostic, text: str) -> str | None:
    found = _record(text, diag.line)
    if found is None:
        return None
    offset, fragment, root = found
    model = root.get("model", "")
    if model == "ir.ui.view":
        edits = _tree_edits_view(fragment, root)
    elif model in ("ir.actions.act_window", "ir.actions.act_window.view"):
        edits = _tree_edits_action(fragment, root, model)
    else:
        return None
    if edits is None:
        return None
    new_fragment = _apply(fragment, edits)
    new_root = _parse(new_fragment)
    if new_root is None or _still_has_tree(new_root, model):
        return None
    return text[:offset] + new_fragment + text[offset + len(fragment) :]


def _literal_span(text: str, node: ast.expr) -> tuple[int, int]:
    starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def offset(line: int, col: int) -> int:
        row = text[starts[line - 1] :].split("\n", 1)[0]
        return starts[line - 1] + len(
            row.encode("utf-8")[:col].decode("utf-8", "replace")
        )

    assert node.end_lineno is not None and node.end_col_offset is not None
    return offset(node.lineno, node.col_offset), offset(
        node.end_lineno, node.end_col_offset
    )


def _fix_tree_py(diag: Diagnostic, text: str) -> str | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    if re.search(r"\r(?!\n)", text):  # lone CR line ends: ast and the offsets disagree
        return None
    edits: list[Edit] = []
    for node, keys in _py_action_dicts(tree):
        if node.lineno != diag.line or not _looks_like_action(keys):
            continue
        literals: list[ast.expr] = []
        mode = keys.get("view_mode")
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            if _TREE_MODE.search(mode.value):
                literals.append(mode)
        views = keys.get("views")
        if isinstance(views, (ast.List, ast.Tuple)):
            for pair in views.elts:
                if (
                    isinstance(pair, (ast.Tuple, ast.List))
                    and len(pair.elts) == 2
                    and isinstance(pair.elts[1], ast.Constant)
                    and pair.elts[1].value == "tree"
                ):
                    literals.append(pair.elts[1])
        for lit in literals:
            start, end = _literal_span(text, lit)
            edits.append(
                (
                    start,
                    end,
                    re.sub(
                        r"(?<=['\",])(\s*)tree(\s*)(?=['\",])",
                        r"\1list\2",
                        text[start:end],
                    ),
                )
            )
    if not edits:
        return text
    new_text = _apply(text, edits)
    try:
        ast.parse(new_text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    return new_text


def fix_view_tree_removed(diag: Diagnostic, text: str) -> str | None:
    """Rename the ``tree`` view type to ``list`` in the record or action dict of a finding."""
    if Path(diag.file_path).suffix.lower() == ".py":
        return _fix_tree_py(diag, text)
    return _fix_tree_xml(diag, text)


default_fixers.register("view-tree-removed", fix_view_tree_removed, migration=True)


# --- search-view-group-attributes ------------------------------------------------------


def fix_search_view_group_attributes(diag: Diagnostic, text: str) -> str | None:
    """Drop ``string`` and ``expand`` from the ``<group>`` of a search view."""
    found = _record(text, diag.line)
    if found is None:
        return None
    offset, fragment, root = found
    arch = _field(root, "arch")
    if arch is None:
        return None
    edits: list[Edit] = []
    for group in _search_groups(arch):
        if not any(a in group.attrib for a in _REJECTED):
            continue
        tag = _tag_of(fragment, root, group)
        if tag is None:
            return None

        def drop(tag_text: str) -> str:
            for attr in _REJECTED:
                tag_text = xt.remove_attr(tag_text, attr)
            return tag_text

        edits.append((tag.start, tag.end, drop(fragment[tag.start : tag.end])))
    new_fragment = _apply(fragment, edits)
    new_root = _parse(new_fragment)
    new_arch = _field(new_root, "arch") if new_root is not None else None
    if new_arch is None or any(
        a in g.attrib for g in _search_groups(new_arch) for a in _REJECTED
    ):
        return None
    return text[:offset] + new_fragment + text[offset + len(fragment) :]


default_fixers.register(
    "search-view-group-attributes", fix_search_view_group_attributes, migration=True
)

# --- chatter-div-removed ---------------------------------------------------------------


def fix_chatter_div_removed(diag: Diagnostic, text: str) -> str | None:
    """Replace ``<div class="oe_chatter">…</div>`` by ``<chatter/>`` where it stood."""
    found = _record(text, diag.line)
    if found is None:
        return None
    offset, fragment, root = found
    arch = _field(root, "arch")
    if arch is None:
        return None
    edits: list[Edit] = []
    for div in arch.iter("div"):
        if "oe_chatter" not in div.get("class", "").split():
            continue
        tag = _tag_of(fragment, root, div)
        closing = xt.end_tag_for(fragment, tag) if tag else None
        if tag is None or not is_plain_chatter_div(div, arch):
            return None
        if closing is None and not tag.self_closing:
            return None
        edits.append((tag.start, closing.end if closing else tag.end, "<chatter/>"))
    new_fragment = _apply(fragment, edits)
    new_root = _parse(new_fragment)
    new_arch = _field(new_root, "arch") if new_root is not None else None
    if new_arch is None or any(
        "oe_chatter" in d.get("class", "").split() for d in new_arch.iter("div")
    ):
        return None
    return text[:offset] + new_fragment + text[offset + len(fragment) :]


default_fixers.register("chatter-div-removed", fix_chatter_div_removed, migration=True)


# --- removed-core-field-usage ----------------------------------------------------------

_QUOTE = r"""(?:['"]|&apos;|&quot;)"""


def fix_removed_core_field_usage(diag: Diagnostic, text: str) -> str | None:
    """Rename a removed field that is only renamed (``MECHANICAL_RENAMES``) at its tag.

    The finding sits on a ``<field name=…>`` (record, view arch or inherit anchor) or on
    an ``<xpath>`` whose ``expr`` names the field; the start tag is found by the line
    it ends on (what lxml reports).
    """
    key = parse_field_title(diag.title)
    if key not in MECHANICAL_RENAMES:
        return None
    old, new = key[1], MECHANICAL_RENAMES[key]
    for tag in xt.tags_ending_on_line(text, diag.line):
        tag_text = text[tag.start : tag.end]
        if tag.name == "field" and xt.get_attr(tag_text, "name") == old:
            fixed = xt.rename_attr_value(tag_text, "name", old, new)
        elif tag.name == "xpath":
            pattern = re.compile(rf"(@name\s*=\s*{_QUOTE}){re.escape(old)}({_QUOTE})")
            expr = xt.get_attr(tag_text, "expr")
            if expr is None or not pattern.search(expr):
                continue
            fixed = xt.set_attr_value(
                tag_text, "expr", pattern.sub(rf"\g<1>{new}\g<2>", expr, 1)
            )
        else:
            continue
        return text[: tag.start] + fixed + text[tag.end :]
    return None


default_fixers.register(
    "removed-core-field-usage",
    fix_removed_core_field_usage,
    migration=True,
    applies=is_mechanical,
)
