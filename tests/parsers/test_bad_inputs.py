"""Parser boundaries return "nothing parsed" for a bad file instead of raising."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    py.write_text("x = " + "not " * 8000 + "1\n")  # RecursionError on every Python
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


N = 60_000  # over the guard (50k), under the 3.10 crash point (~136k): safe to scan anywhere

BYPASS_SHAPES = {
    "binop": lambda n: "x = " + " + ".join(["1"] * n),
    "attr": lambda n: "x = a" + ".b" * n,
    "subscript": lambda n: "x = a" + "[0]" * n,
    "call_args": lambda n: "x = f" + "(1,2)" * n,
    "slice": lambda n: "x = a" + "[1:2]" * n,
    "call_kwargs": lambda n: "x = f" + "(a=1)" * n,
    "call_dict": lambda n: "x = f" + "({})" * n,
    "in_parens": lambda n: "x = (1" + "+1" * n + ")",
    "in_kwarg": lambda n: "x = f(a=1" + "+1" * n + ")",
    "in_dict_value": lambda n: "x = {1: 1" + "+1" * n + "}",
    "fstring_binop": lambda n: 'x = f"{' + "+".join(["1"] * n) + '}"',
    "fstring_attr": lambda n: 'x = f"{a' + ".b" * n + '}"',
    "rf_string_call": lambda n: 'x = rf"{f' + "()" * n + '}"',
}


@pytest.mark.parametrize("shape", sorted(BYPASS_SHAPES))
def test_chain_guard_catches_every_known_shape(shape: str):
    from odoo_doctor.core.source import chain_too_long

    assert chain_too_long(BYPASS_SHAPES[shape](N) + "\n")


def test_chain_guard_thresholds():
    from odoo_doctor.core.source import chain_too_long

    assert not chain_too_long("x = " + " + ".join(["1"] * 10_000) + "\n")  # small file
    assert not chain_too_long(
        "x = " + " + ".join(["1"] * 30_000) + "\n"
    )  # under the limit
    assert chain_too_long("x = " + " + ".join(["1"] * 50_002) + "\n")


@pytest.mark.parametrize(
    "legit",
    [
        "x = [" + ", ".join(["1.5"] * 200_000) + "]",
        "x = [" + ", ".join(["a + b"] * 100_000) + "]",
        "x = {" + ", ".join(f'"k{i}": f(1, 2)(3)' for i in range(50_000)) + "}",
        "x = {" + ", ".join(f'"k{i}": [a.b.c, d[1:2]]' for i in range(50_000)) + "}",
        "x = (" + " ".join(['"a"'] * 200_000) + ")",
        "\n".join(f"y{i} = a.b.c + d[0] + f(1)(2)" for i in range(60_000)),
        "f(" + ", ".join(f"a{i}=1+2" for i in range(60_000)) + ")",
    ],
)
def test_chain_guard_does_not_skip_legitimate_big_files(legit: str):
    from odoo_doctor.core.source import chain_too_long

    assert len(legit) >= 100_000 and not chain_too_long(legit + "\n")
