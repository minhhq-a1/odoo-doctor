# src/odoo_doctor/parsers/xml_records.py
"""Parse XML records, views, and data files using lxml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class XmlIdInfo:
    xml_id: str             # "module.xml_id"
    model: str | None
    record_type: str        # "record", "template", "menuitem", etc.
    file_path: str
    line: int
    refs: list[str] = field(default_factory=list)  # referenced xml IDs


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

        # Collect ref attributes
        for child in elem.iter():
            ref = child.get("ref")
            if ref:
                refs.append(ref)

        records.append(XmlIdInfo(
            xml_id=full_id,
            model=model,
            record_type=elem.tag,
            file_path=str(file_path),
            line=elem.sourceline or 0,
            refs=refs,
        ))

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

        for field_elem in record.findall("field"):
            fname = field_elem.get("name")
            if fname == "model":
                model = (field_elem.text or "").strip()
            elif fname == "inherit_id":
                inherit_id = field_elem.get("ref")
            elif fname == "arch":
                # Parse the arch content for field/button refs
                _extract_arch_refs(field_elem, field_refs, button_methods)

        if not model:
            continue

        views.append(ViewInfo(
            xml_id=xml_id,
            model=model,
            inherit_id=inherit_id,
            field_refs=field_refs,
            button_methods=button_methods,
            file_path=str(file_path),
            line=record.sourceline or 0,
        ))

    return views


def _extract_arch_refs(
    arch_elem: etree._Element,
    field_refs: list[str],
    button_methods: list[str],
) -> None:
    """Walk arch XML to find <field name="..."> and <button name="..." type="object">."""
    for elem in arch_elem.iter():
        if elem.tag == "field":
            name = elem.get("name")
            if name and name not in field_refs:
                field_refs.append(name)
        elif elem.tag == "button":
            btn_name = elem.get("name")
            btn_type = elem.get("type")
            if btn_name and btn_type == "object" and btn_name not in button_methods:
                button_methods.append(btn_name)
