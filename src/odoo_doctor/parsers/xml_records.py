# src/odoo_doctor/parsers/xml_records.py
"""Parse XML records, views, and data files using lxml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

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


_REF_CALL_RE = re.compile(r"\bref\(['\"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)['\"]\)")


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
        if xml_id is None:
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
            )
        )

    return views


def _extract_arch_refs(
    arch_elem: etree._Element,
    field_refs: list[str],
    button_methods: list[str],
    field_ref_lines: dict[str, int],
    button_method_lines: dict[str, int],
) -> None:
    """Walk arch XML for <field name="..."> and <button ... type="object">.

    A <field>/<button> nested inside another <field> belongs to a related
    comodel (inline subview), not to this view's model, so it is not attributed
    here. (Spec A5: never check a field against the wrong model.)
    """

    def walk(elem: etree._Element, inside_field: bool) -> None:
        for child in elem:
            if child.tag == "field":
                if not inside_field:
                    name = child.get("name")
                    if name:
                        if name not in field_refs:
                            field_refs.append(name)
                        field_ref_lines.setdefault(name, child.sourceline or 0)
                walk(child, True)
            elif child.tag == "button":
                if not inside_field:
                    btn_name = child.get("name")
                    btn_type = child.get("type")
                    if btn_name and btn_type == "object":
                        if btn_name not in button_methods:
                            button_methods.append(btn_name)
                        button_method_lines.setdefault(btn_name, child.sourceline or 0)
                walk(child, inside_field)
            else:
                walk(child, inside_field)

    walk(arch_elem, False)
