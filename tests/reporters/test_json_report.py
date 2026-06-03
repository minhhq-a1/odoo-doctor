# tests/reporters/test_json_report.py
"""Tests for JSON reporter."""

from __future__ import annotations

import json

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.json_report import render_json


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_json_valid():
    diags = [_diag()]
    scores = {"m": ScoreResult(75.0, "Good", [CategoryScore("Security", 75, 1, 25.0)], ["Security"], 1)}
    output = render_json(diags, scores)
    parsed = json.loads(output)
    assert "modules" in parsed
    assert parsed["modules"]["m"]["score"]["overall"] == 75.0
    assert len(parsed["modules"]["m"]["diagnostics"]) == 1


def test_render_json_empty():
    output = render_json([], {})
    parsed = json.loads(output)
    assert parsed["modules"] == {}
