"""JSON top_findings should advertise fixability for agents."""

from __future__ import annotations

import json

from odoo_doctor import __version__
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import ScoreResult, score_diagnostics
from odoo_doctor.reporters.json_report import render_json


def test_top_findings_include_fixable_flag():
    d = Diagnostic(
        module="m",
        file_path="m/__manifest__.py",
        line=1,
        column=0,
        rule="manifest-missing-required-fields",
        category="Module Hygiene",
        severity="warning",
        tier="P2",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="help",
        odoo_version="17.0",
    )
    scores = {"m": score_diagnostics([d], [True])}
    out = json.loads(render_json([d], scores))
    finding = out["top_findings"][0]
    assert finding["rule"] == "manifest-missing-required-fields"
    assert finding["fixable"] is True


def test_json_includes_score_schema_version():
    from odoo_doctor.core.scoring import ScoreResult

    scores = {
        "mod": ScoreResult(
            overall=100.0,
            label="Excellent",
            categories=[],
            in_scope_categories=[],
            diagnostics_counted=0,
        )
    }
    output = json.loads(render_json([], scores))
    assert output["score_schema_version"] == 2
    assert output["version"] == __version__


def test_render_json_is_the_serialized_build_payload():
    from odoo_doctor.core.scoring import ScoreResult
    from odoo_doctor.reporters.json_report import build_payload

    scores = {
        "mod": ScoreResult(
            overall=100.0,
            label="Excellent",
            categories=[],
            in_scope_categories=[],
            diagnostics_counted=0,
        )
    }
    payload = build_payload([], scores)
    assert isinstance(payload, dict)
    assert payload["project_score"]["overall"] == 100.0
    assert render_json([], scores) == json.dumps(payload, indent=2)


def test_project_score_carries_the_secondary_numbers():
    scores = {
        "a": ScoreResult(
            100.0, "x", [], [], 0, python_lines=300, overall_with_medium=100.0
        ),
        "b": ScoreResult(
            80.0, "x", [], [], 0, python_lines=100, overall_with_medium=60.0
        ),
    }
    ps = json.loads(render_json([], scores))["project_score"]
    assert (ps["overall"], ps["weighted"], ps["with_medium"]) == (90.0, 95.0, 80.0)
