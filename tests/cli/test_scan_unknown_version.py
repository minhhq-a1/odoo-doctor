"""A scan whose Odoo version cannot be detected still runs the native rules.

Detection reads --odoo-version, the config, then a manifest version shaped like 17.0.x.y.z.
A custom addon versioned ``1.0`` with no config gave ``unknown``, which switched off every
rule that declares ``min_version`` (36 of the 37 native rules): the report said 100, Excellent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _addon(root: Path, manifest_version: str) -> Path:
    addon = root / "mod"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": "M",
                "version": manifest_version,
                "depends": ["base"],
                "data": [],
                "license": "LGPL-3",
            }
        )
    )
    (addon / "__init__.py").write_text("from . import m\n")
    (addon / "m.py").write_text(
        "from odoo import models\n\n\n"
        "class M(models.Model):\n"
        "    _name = 'x.m'\n\n"
        "    def run(self, expr):\n"
        "        return eval(expr)\n"
    )
    return addon


def _scan(cwd: Path, *args: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_doctor.cli.app import app; app()",
            "scan",
            str(cwd),
            "--json",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return json.loads(result.stdout)


def _rules(report: dict) -> set[str]:
    return {
        d["rule"]
        for module in report["modules"].values()
        for d in module["diagnostics"]
        if d["source"] == "native"
    }


def test_an_addon_versioned_1_0_without_config_still_gets_native_findings(tmp_path):
    _addon(tmp_path, "1.0")
    assert "eval-usage" in _rules(_scan(tmp_path))


def test_an_explicit_version_gives_the_same_native_findings(tmp_path):
    _addon(tmp_path, "1.0")
    assert _rules(_scan(tmp_path)) == _rules(_scan(tmp_path, "--odoo-version", "19.0"))
