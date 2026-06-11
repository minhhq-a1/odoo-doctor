"""`scan --format sarif` prints a SARIF log."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def _addon(root: Path) -> None:
    mod = root / "my_addon"
    mod.mkdir()
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], 'data': []}"
    )


def test_scan_format_sarif(tmp_path: Path):
    _addon(tmp_path)
    result = runner.invoke(app, ["scan", str(tmp_path), "--format", "sarif"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["tool"]["driver"]["name"] == "odoo-doctor"
