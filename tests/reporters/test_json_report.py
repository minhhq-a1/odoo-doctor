# tests/reporters/test_json_report.py
"""Tests for JSON reporter."""

from __future__ import annotations

import json

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.json_report import render_json


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m",
        file_path="f.py",
        line=1,
        column=0,
        rule="r",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="h",
        odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_json_valid():
    diags = [_diag()]
    scores = {
        "m": ScoreResult(
            75.0, "Good", [CategoryScore("Security", 75, 1, 25.0)], ["Security"], 1
        )
    }
    output = render_json(diags, scores)
    parsed = json.loads(output)
    assert "modules" in parsed
    assert parsed["project_score"]["overall"] == 75.0
    assert parsed["project_score"]["label"] == "Good"
    assert parsed["project_score"]["module_count"] == 1
    assert parsed["modules"]["m"]["score"]["overall"] == 75.0
    assert len(parsed["modules"]["m"]["diagnostics"]) == 1


def test_render_json_empty():
    output = render_json([], {})
    parsed = json.loads(output)
    assert parsed["modules"] == {}
    assert parsed["project_score"]["overall"] == 100.0
    assert parsed["project_score"]["label"] == "Excellent"
    assert parsed["project_score"]["module_count"] == 0


def test_render_json_project_score_aggregates_modules():
    scores = {
        "clean": ScoreResult(100.0, "Excellent", [], [], 0),
        "bad": ScoreResult(50.0, "Needs work", [], [], 3),
    }
    output = render_json([], scores)
    parsed = json.loads(output)
    assert parsed["project_score"]["overall"] == 75.0
    assert parsed["project_score"]["label"] == "Good"
    assert parsed["project_score"]["module_count"] == 2


def test_render_json_top_findings_multi_module():
    d1 = _diag(module="mod_a", tier="P0", title="SQL injection")
    d2 = _diag(module="mod_b", tier="P1", title="Missing access", line=2, rule="r2")
    scores = {
        "mod_a": ScoreResult(50.0, "Needs work", [], [], 1),
        "mod_b": ScoreResult(70.0, "Needs work", [], [], 1),
    }
    output = render_json([d1, d2], scores)
    parsed = json.loads(output)
    assert "top_findings" in parsed
    assert len(parsed["top_findings"]) == 2
    assert parsed["top_findings"][0]["tier"] == "P0"


def test_render_json_top_findings_empty():
    output = render_json([], {})
    parsed = json.loads(output)
    assert parsed["top_findings"] == []


def test_render_json_has_schema_version():
    parsed = json.loads(render_json([], {}))
    assert parsed["schema_version"] == "1.0"


def test_render_json_has_version():
    parsed = json.loads(render_json([], {}))
    assert parsed["version"] == "0.2.0"


def test_render_json_top_findings_have_full_fields():
    d = _diag(tier="P0")
    scores = {
        "m": ScoreResult(
            50.0,
            "Needs work",
            [CategoryScore("Security", 75, 1, 25.0)],
            ["Security"],
            1,
        )
    }
    parsed = json.loads(render_json([d], scores))
    tf = parsed["top_findings"][0]
    for key in (
        "module",
        "file_path",
        "line",
        "rule",
        "tier",
        "title",
        "category",
        "severity",
        "confidence",
    ):
        assert key in tf, f"top_findings missing {key}"
    # Parity with the corresponding modules[*].diagnostics[*] entry
    diag = parsed["modules"]["m"]["diagnostics"][0]
    assert tf["category"] == diag["category"]
    assert tf["severity"] == diag["severity"]
    assert tf["confidence"] == diag["confidence"]


def test_render_json_project_score_rounded():
    scores = {"a": ScoreResult(99.5142857, "Excellent", [], [], 1)}
    parsed = json.loads(render_json([], scores))
    assert parsed["project_score"]["overall"] == 99.5
