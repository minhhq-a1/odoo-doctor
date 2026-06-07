# tests/integration/test_crash_safety.py
"""A module containing a non-UTF-8 file scans to completion (Part B / B1)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_scan_completes_with_non_utf8_file(tmp_path: Path):
    mod = tmp_path / "enc_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Enc", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("")
    # A non-UTF-8 source file (latin-1 'é') must not abort the scan
    (mod / "broken_enc.py").write_bytes(b"# -*- coding: latin-1 -*-\nNAME = '\xe9'\n")
    # A valid model file that must still be analyzed
    (mod / "good.py").write_text(
        "from odoo import models, fields\n\n"
        "class Foo(models.Model):\n"
        "    _name = 'foo.bar'\n"
        "    name = fields.Char()\n"
    )

    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "enc_mod" in parsed["modules"]
