"""One bad input file must never abort a scan or hide the findings of other files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()

GOOD_PY = "def run(self, expr):\n    return eval(expr)\n"
MANIFEST = "{'name': 'Mod', 'version': '17.0.1.0.0', 'depends': ['base'], %s}"


def _addon(root: Path, name: str, manifest: str | None = None) -> Path:
    mod = root / name
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(manifest or MANIFEST % "'data': []")
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import good\n")
    (mod / "models" / "good.py").write_text(GOOD_PY)
    return mod


def _scan(root: Path) -> tuple[set[str], list[str]]:
    """(rules reported, WARN lines on stderr); stdout must be the pure JSON report."""
    result = runner.invoke(app, ["scan", str(root), "--json"])
    assert result.exit_code in (0, 1), (result.output, result.exception)
    assert result.exception is None or isinstance(result.exception, SystemExit), repr(
        result.exception
    )
    report = json.loads(result.stdout)
    rules = {d["rule"] for m in report["modules"].values() for d in m["diagnostics"]}
    return rules, [
        ln for ln in result.stderr.splitlines() if ln.startswith("[WARN] skipped")
    ]


def test_malformed_manifest_values(tmp_path: Path):
    _addon(tmp_path, "none_data", MANIFEST % "'data': None")
    _addon(tmp_path, "int_depends", "{'name': 'M', 'depends': 5, 'data': []}")
    _addon(tmp_path, "unhashable", "{'name': 'M', ['a']: 1}")
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules
    assert len(warns) == 1 and "unhashable/__manifest__.py" in warns[0]


@pytest.mark.parametrize(
    "extra",
    [
        "'version': 7",
        "'version': ['a']",
        "'external_dependencies': {'python': 5}",
        "'external_dependencies': 5",
        "'external_dependencies': ['x']",
    ],
)
def test_odd_manifest_value_types(tmp_path: Path, extra: str):
    _addon(
        tmp_path, "mod", f"{{'name': 'M', 'depends': ['base'], 'data': [], {extra}}}"
    )
    assert "eval-usage" in _scan(tmp_path)[0]


def test_xml_declared_utf8_with_latin1_bytes(tmp_path: Path):
    mod = _addon(tmp_path, "mod", MANIFEST % "'data': ['views/v.xml']")
    (mod / "views").mkdir()
    (mod / "views" / "v.xml").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n<odoo><record id="r" model="x">'
        b'<field name="name">caf\xe9</field></record></odoo>'
    )
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules
    assert len(warns) == 1 and "v.xml" in warns[0]


def test_python_file_too_deep_for_the_parser(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    # right-nested: RecursionError on every supported Python
    (mod / "models" / "deep.py").write_text("x = " + "not " * 8000 + "1\n")
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules
    assert len(warns) == 1 and "deep.py" in warns[0]


def test_python_file_with_a_huge_operator_chain_is_skipped_by_the_guard(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    # 240 KB, 60k links: parseable on 3.12+ (RecursionError) and on 3.10, but over the guard
    (mod / "models" / "long.py").write_text("x = " + " + ".join(["1"] * 60_000) + "\n")
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules
    assert len(warns) == 1 and "long.py" in warns[0] and "too long" in warns[0]


def test_access_csv_not_utf8_or_short_rows(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    (mod / "security").mkdir()
    csv_file = mod / "security" / "ir.model.access.csv"
    csv_file.write_bytes(
        b"id,name,model_id:id,perm_read\nshort\nok,caf\xe9,model_x,1\n"
    )
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules
    assert len(warns) == 1 and "ir.model.access.csv" in warns[0]

    csv_file.write_bytes(b"id,name,model_id:id\nshort\n,,\n")  # short rows, valid UTF-8
    rules, warns = _scan(tmp_path)
    assert "eval-usage" in rules and warns == []


def test_skipped_file_warnings_are_capped(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    for i in range(30):
        (mod / "models" / f"d{i}.py").write_text("x = " + "not " * 8000 + "1\n")
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code in (0, 1)
    json.loads(result.stdout)
    lines = [ln for ln in result.stderr.splitlines() if ln.startswith("[WARN] ")]
    assert (
        len(
            [
                ln
                for ln in lines
                if "skipped /" in ln or "skipped " in ln and "more" not in ln
            ]
        )
        == 20
    )
    assert lines[-1] == "[WARN] ... and 10 more skipped"


def test_addon_name_with_brackets_in_terminal_report(tmp_path: Path):
    _addon(tmp_path, "my[addon]")
    _addon(tmp_path, "[red]second")
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code in (0, 1), (result.output, repr(result.exception))
    out = re.sub(r"\x1b\[[0-9;]*m", "", result.output).replace("\n", "")
    assert "Findings for my[addon]" in out
    assert "Findings for [red]second" in out
    assert "my[addon]/__manifest__.py" in out
