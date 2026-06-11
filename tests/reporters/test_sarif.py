"""SARIF reporter emits a valid 2.1.0 log."""

from __future__ import annotations

import json

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.reporters.sarif import render_sarif


def _diag(**over) -> Diagnostic:
    base = dict(
        module="m",
        file_path="m/models/x.py",
        line=12,
        column=4,
        rule="eval-usage",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="Use of builtin eval()",
        message="eval is dangerous",
        help="avoid eval",
        odoo_version="17.0",
    )
    base.update(over)
    return Diagnostic(**base)


def test_sarif_has_required_top_level_keys():
    out = json.loads(render_sarif([_diag()], base_path=None))
    assert out["version"] == "2.1.0"
    assert "$schema" in out
    assert out["runs"][0]["tool"]["driver"]["name"] == "odoo-doctor"


def test_sarif_maps_severity_to_level():
    out = json.loads(render_sarif([_diag(severity="error")], base_path=None))
    result = out["runs"][0]["results"][0]
    assert result["level"] == "error"
    assert result["ruleId"] == "eval-usage"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["region"]["startLine"] == 12


def test_sarif_registers_rules_in_driver():
    out = json.loads(render_sarif([_diag()], base_path=None))
    rule_ids = [r["id"] for r in out["runs"][0]["tool"]["driver"]["rules"]]
    assert "eval-usage" in rule_ids


def test_sarif_empty_is_valid():
    out = json.loads(render_sarif([], base_path=None))
    assert out["runs"][0]["results"] == []
