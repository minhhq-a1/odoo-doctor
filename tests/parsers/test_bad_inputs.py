"""Parser boundaries return "nothing parsed" for a bad file instead of raising."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.source import clear_source_cache, parse_python
from odoo_doctor.discovery.addons import discover_addons
from odoo_doctor.parsers.manifest import parse_manifest
from odoo_doctor.parsers.security_csv import parse_access_csv
from odoo_doctor.parsers.xml_records import parse_views, parse_xml_records
from odoo_doctor.rules.suppression import scan_xml_suppressions


def test_manifest_with_unhashable_key(tmp_path: Path):
    (tmp_path / "__manifest__.py").write_text("{'name': 'M', ['a']: 1}")
    assert parse_manifest(tmp_path) is None
    assert discover_addons([tmp_path]) == []


def test_manifest_with_wrong_value_types(tmp_path: Path):
    (tmp_path / "__manifest__.py").write_text(
        "{'name': 'M', 'depends': 5, 'data': None}"
    )
    manifest = parse_manifest(tmp_path)
    assert manifest is not None
    assert manifest.depends == [] and manifest.data == []


def test_manifest_lists_keep_only_strings(tmp_path: Path):
    (tmp_path / "__manifest__.py").write_text(
        "{'name': 'M', 'depends': ['base', 3, ['x']], 'data': ('a.xml',)}"
    )
    manifest = parse_manifest(tmp_path)
    assert manifest.depends == ["base"] and manifest.data == ["a.xml"]


def test_xml_with_invalid_utf8_bytes(tmp_path: Path):
    xml = tmp_path / "v.xml"
    xml.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?><odoo>caf\xe9</odoo>')
    assert parse_xml_records(xml, "m") == []
    assert parse_views(xml, "m") == []
    assert scan_xml_suppressions(xml) == set()


def test_python_that_blows_the_parser_stack(tmp_path: Path):
    py = tmp_path / "deep.py"
    py.write_text("x = " + "(" * 5000 + "1" + ")" * 5000 + "\n")
    clear_source_cache()
    assert parse_python(py) is None


def test_access_csv_with_non_utf8_and_short_rows(tmp_path: Path):
    csv_file = tmp_path / "ir.model.access.csv"
    csv_file.write_bytes(
        b"id,name,model_id:id,perm_read\nshort\n,,\nok,caf\xe9,model_x,1\n"
    )
    rules = parse_access_csv(csv_file, "m")
    assert [r.id for r in rules] == ["short", "", "ok"]
    assert rules[-1].perm_read and rules[0].model_external_id == ""


def test_access_csv_with_nul_byte(tmp_path: Path):
    csv_file = tmp_path / "ir.model.access.csv"
    csv_file.write_bytes(b"id,name\na,b\x00c\n")
    parse_access_csv(csv_file, "m")  # must not raise
