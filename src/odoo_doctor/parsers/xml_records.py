# src/odoo_doctor/parsers/xml_records.py
"""Parse XML records, views, and data files using lxml."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class XmlIdInfo:
    xml_id: str  # "module.xml_id"
    model: str | None
    record_type: str  # "record", "template", "menuitem", etc.
    file_path: str
    line: int
    refs: list[str] = field(default_factory=list)  # referenced xml IDs
    ref_lines: dict[str, int] = field(default_factory=dict)
    noupdate: bool = False


@dataclass
class ViewInfo:
    xml_id: str
    model: str
    view_type: str | None = None
    inherit_id: str | None = None
    field_refs: list[str] = field(default_factory=list)
    button_methods: list[str] = field(default_factory=list)
    file_path: str = ""
    line: int = 0
    field_ref_lines: dict[str, int] = field(default_factory=dict)
    button_method_lines: dict[str, int] = field(default_factory=dict)
    # For refs inserted by an <xpath> that targets a field node: ref -> that field's name
    # (None when the ref is not anchored, or seen with different anchors).
    field_ref_anchors: dict[str, str | None] = field(default_factory=dict)
    button_method_anchors: dict[str, str | None] = field(default_factory=dict)


_REF_CALL_RE = re.compile(r"\bref\(['\"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)['\"]\)")


# Elements a data file nests its records in; a <menuitem> may also nest <menuitem>s.
_DATA_CONTAINERS = frozenset({"odoo", "openerp", "data"})


def _defines_xml_id(elem: etree._Element) -> bool:
    """Does *elem* (which has an ``id``) define a record, or is it markup inside one?

    Only elements at the data level do: children of ``<odoo>``/``<data>`` and nested
    ``<menuitem>``s. An ``id`` on a ``<div>``, ``<span>`` or ``<setting>`` inside a template
    or an arch is an HTML/QWeb id, and ``<delete id=...>`` removes a record, it defines none.
    """
    if elem.tag == "delete":
        return False
    parent = elem.getparent()
    if parent is None:
        return False
    allowed = (
        _DATA_CONTAINERS | {"menuitem"} if elem.tag == "menuitem" else _DATA_CONTAINERS
    )
    while parent is not None:
        if parent.tag not in allowed:
            return False
        parent = parent.getparent()
    return True


def parse_xml_records(file_path: Path, module_name: str) -> list[XmlIdInfo]:
    """Extract all XML IDs from an Odoo data/view file."""
    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return []

    root = tree.getroot()
    records: list[XmlIdInfo] = []

    for elem in root.iter():
        xml_id = elem.get("id")
        if xml_id is None or not _defines_xml_id(elem):
            continue

        full_id = f"{module_name}.{xml_id}" if "." not in xml_id else xml_id

        model = None
        refs: list[str] = []

        if elem.tag == "record":
            model = elem.get("model")
        elif elem.tag == "menuitem":
            model = "ir.ui.menu"
        elif elem.tag == "template":
            model = "ir.ui.view"

        # Check noupdate context — look at parent elements
        noupdate = False
        parent = elem.getparent()
        while parent is not None:
            nu = parent.get("noupdate")
            if nu is not None:
                noupdate = nu == "1" or nu.lower() == "true"
                break
            parent = parent.getparent()

        ref_lines: dict[str, int] = {}
        # Collect ref attributes and eval ref patterns
        for child in elem.iter():
            if child.tag == "field" and child.get("name") == "inherit_id":
                continue  # View inherit_id is handled with view context.
            ref = child.get("ref")
            if ref:
                refs.append(ref)
                ref_lines.setdefault(ref, child.sourceline or 0)
            eval_attr = child.get("eval")
            if eval_attr:
                for match in _REF_CALL_RE.findall(eval_attr):
                    refs.append(match)
                    ref_lines.setdefault(match, child.sourceline or 0)

        records.append(
            XmlIdInfo(
                xml_id=full_id,
                model=model,
                record_type=elem.tag,
                file_path=str(file_path),
                line=elem.sourceline or 0,
                refs=refs,
                ref_lines=ref_lines,
                noupdate=noupdate,
            )
        )

    return records


def parse_views(file_path: Path, module_name: str) -> list[ViewInfo]:
    """Extract view definitions (ir.ui.view records) with field/button references."""
    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return []

    root = tree.getroot()
    views: list[ViewInfo] = []

    for record in root.iter("record"):
        if record.get("model") != "ir.ui.view":
            continue

        xml_id_raw = record.get("id", "")
        xml_id = f"{module_name}.{xml_id_raw}" if "." not in xml_id_raw else xml_id_raw

        model = ""
        inherit_id = None
        field_refs: list[str] = []
        button_methods: list[str] = []
        field_ref_lines: dict[str, int] = {}
        button_method_lines: dict[str, int] = {}
        field_ref_anchors: dict[str, str | None] = {}
        button_method_anchors: dict[str, str | None] = {}

        for field_elem in record.findall("field"):
            fname = field_elem.get("name")
            if fname == "model":
                model = (field_elem.text or "").strip()
            elif fname == "inherit_id":
                inherit_id = field_elem.get("ref")
            elif fname == "arch":
                # Parse the arch content for field/button refs
                _extract_arch_refs(
                    field_elem,
                    field_refs,
                    button_methods,
                    field_ref_lines,
                    button_method_lines,
                    field_ref_anchors,
                    button_method_anchors,
                )

        if not model:
            continue

        views.append(
            ViewInfo(
                xml_id=xml_id,
                model=model,
                inherit_id=inherit_id,
                field_refs=field_refs,
                button_methods=button_methods,
                file_path=str(file_path),
                line=record.sourceline or 0,
                field_ref_lines=field_ref_lines,
                button_method_lines=button_method_lines,
                field_ref_anchors=field_ref_anchors,
                button_method_anchors=button_method_anchors,
            )
        )

    return views


# Root tags of a view; one that is not the first step of an xpath is an inline subview.
_VIEW_TAGS = frozenset(
    {
        "list",
        "tree",
        "form",
        "kanban",
        "graph",
        "pivot",
        "calendar",
        "gantt",
        "map",
        "activity",
        "cohort",
        "search",
    }
)
_STEP_TAG = re.compile(r"[A-Za-z_][\w.-]*")


def _xpath_steps(expr: str) -> list[str]:
    """Split an xpath on ``/`` outside predicates and quotes (``//a/b[@x='/']`` -> a, b)."""
    steps: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    for ch in expr:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch == "/" and depth == 0:
            if current:
                steps.append("".join(current))
                current = []
        else:
            depth += ch == "["
            depth -= ch == "]"
            current.append(ch)
    if current:
        steps.append("".join(current))
    return steps


def _xpath_enters_subview(expr: str) -> bool:
    """Does an inherited-view xpath target a node inside an x2many's inline subview?

    Then what it inserts belongs to the comodel, not to the view's model. That is the
    case when the path goes through a ``field`` step (``//field[@name='lines']//list//...``)
    or through a view tag that is not its first step (``//page[@name='x']//list/field``).
    A view tag as the first step is the root of a view of this model (``//list/field``).
    """
    steps = _xpath_steps(expr)
    for index, step in enumerate(steps):
        match = _STEP_TAG.match(step)
        if match is None:
            continue
        tag = match.group(0)
        if tag == "field" and index < len(steps) - 1:
            return True
        if index > 0 and tag in _VIEW_TAGS:
            return True
    return False


_FIELD_STEP = re.compile(r"""field\[@name=['"]([^'"]+)['"]\]""")


def _targeted_field(expr: str) -> str | None:
    """The field an xpath ends on (``//field[@name='pattern']`` -> ``pattern``), if any."""
    steps = _xpath_steps(expr)
    match = _FIELD_STEP.match(steps[-1]) if steps else None
    return match.group(1) if match else None


def _note_anchor(anchors: dict[str, str | None], name: str, anchor: str | None) -> None:
    """Keep an anchor only while every sighting of *name* has the same one."""
    if name not in anchors:
        anchors[name] = anchor
    elif anchors[name] != anchor:
        anchors[name] = None


def _extract_arch_refs(
    arch_elem: etree._Element,
    field_refs: list[str],
    button_methods: list[str],
    field_ref_lines: dict[str, int],
    button_method_lines: dict[str, int],
    field_ref_anchors: dict[str, str | None],
    button_method_anchors: dict[str, str | None],
) -> None:
    """Walk arch XML for <field name="..."> and <button ... type="object">.

    A <field>/<button> nested inside another <field> belongs to a related
    comodel (inline subview), not to this view's model, so it is not attributed
    here. (Spec A5: never check a field against the wrong model.) The same goes for
    what an <xpath> inserts into such a subview, and a field/button carrying a
    ``position`` attribute only locates a node of the parent view (which may sit in
    one of its subviews), so it is not a reference either.
    """

    def walk(elem: etree._Element, inside_field: bool, anchor: str | None) -> None:
        for child in elem:
            if child.tag == "xpath":
                expr = child.get("expr", "")
                walk(
                    child,
                    inside_field or _xpath_enters_subview(expr),
                    _targeted_field(expr),
                )
            elif child.tag == "groupby":
                # a list view's group header: its fields and buttons act on the group's record
                walk(child, True, anchor)
            elif child.tag == "field":
                if not inside_field and child.get("position") is None:
                    name = child.get("name")
                    if name:
                        if name not in field_refs:
                            field_refs.append(name)
                        field_ref_lines.setdefault(name, child.sourceline or 0)
                        _note_anchor(field_ref_anchors, name, anchor)
                walk(child, True, anchor)
            elif child.tag == "button":
                if not inside_field and child.get("position") is None:
                    btn_name = child.get("name")
                    btn_type = child.get("type")
                    if btn_name and btn_type == "object":
                        if btn_name not in button_methods:
                            button_methods.append(btn_name)
                        button_method_lines.setdefault(btn_name, child.sourceline or 0)
                        _note_anchor(button_method_anchors, btn_name, anchor)
                walk(child, inside_field, anchor)
            else:
                walk(child, inside_field, anchor)

    walk(arch_elem, False, None)
