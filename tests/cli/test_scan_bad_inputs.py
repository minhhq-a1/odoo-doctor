"""One bad input file must never abort a scan or hide the findings of other files."""

from __future__ import annotations

import json
import re
from pathlib import Path

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


def _scan_rules(root: Path) -> set[str]:
    result = runner.invoke(app, ["scan", str(root), "--json"])
    assert result.exit_code in (0, 1), (result.output, result.exception)
    assert not isinstance(result.exception, Exception) or isinstance(
        result.exception, SystemExit
    ), repr(result.exception)
    report = json.loads(result.stdout)
    return {d["rule"] for m in report["modules"].values() for d in m["diagnostics"]}


def test_malformed_manifest_values(tmp_path: Path):
    _addon(tmp_path, "none_data", MANIFEST % "'data': None")
    _addon(tmp_path, "int_depends", "{'name': 'M', 'depends': 5, 'data': []}")
    _addon(tmp_path, "unhashable", "{'name': 'M', ['a']: 1}")
    assert "eval-usage" in _scan_rules(tmp_path)


def test_xml_declared_utf8_with_latin1_bytes(tmp_path: Path):
    mod = _addon(tmp_path, "mod", MANIFEST % "'data': ['views/v.xml']")
    (mod / "views").mkdir()
    (mod / "views" / "v.xml").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n<odoo><record id="r" model="x">'
        b'<field name="name">caf\xe9</field></record></odoo>'
    )
    assert "eval-usage" in _scan_rules(tmp_path)


def test_python_file_too_deep_for_the_parser(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    (mod / "models" / "deep.py").write_text(
        "x = " + "(" * 5000 + "1" + ")" * 5000 + "\n"
    )
    (mod / "models" / "nul.py").write_text("x = 1\x00\n")
    (mod / "models" / "long.py").write_text("x = " + " + ".join(["1"] * 200000) + "\n")
    assert "eval-usage" in _scan_rules(tmp_path)


def test_access_csv_not_utf8_or_short_rows(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    (mod / "security").mkdir()
    (mod / "security" / "ir.model.access.csv").write_bytes(
        b"id,name,model_id:id,perm_read\nshort\nok,caf\xe9,model_x,1\n"
    )
    assert "eval-usage" in _scan_rules(tmp_path)

    (mod / "security" / "ir.model.access.csv").write_bytes(
        b"id,name,model_id:id\nshort\n,,\n"
    )
    assert "eval-usage" in _scan_rules(tmp_path)


def test_addon_name_with_brackets_in_terminal_report(tmp_path: Path):
    _addon(tmp_path, "my[addon]")
    _addon(tmp_path, "[red]second")
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code in (0, 1), (result.output, repr(result.exception))
    out = re.sub(r"\x1b\[[0-9;]*m", "", result.output).replace("\n", "")
    assert "Findings for my[addon]" in out
    assert "Findings for [red]second" in out
    assert "my[addon]/__manifest__.py" in out
