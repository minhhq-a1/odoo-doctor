# tests/reporters/test_terminal.py
"""Tests for terminal reporter."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.terminal import render_terminal


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="raw-sql",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="SQL injection",
        message="cr.execute uses f-string",
        help="Use params",
        odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_terminal_returns_string():
    diags = [_diag()]
    score = ScoreResult(
        overall=75.0,
        label="Good",
        categories=[CategoryScore("Security", 75, 1, 25.0)],
        in_scope_categories=["Security"],
        diagnostics_counted=1,
    )
    output = render_terminal(diags, {"sale_custom": score})
    assert "sale_custom" in output
    assert "75" in output
    assert "SQL injection" in output


def test_render_terminal_empty():
    output = render_terminal([], {})
    assert "No diagnostics" in output or "clean" in output.lower()


def test_render_terminal_shows_project_score_for_multiple_modules():
    clean = ScoreResult(
        overall=100.0,
        label="Excellent",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=0,
    )
    bad = ScoreResult(
        overall=50.0,
        label="Needs work",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=2,
    )

    output = render_terminal([], {"clean": clean, "bad": bad})

    assert "Project Score:" in output
    assert "75" in output
    assert "100" in output
    assert "Good" in output


def test_render_terminal_omits_project_score_for_single_module():
    score = ScoreResult(
        overall=100.0,
        label="Excellent",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=0,
    )

    output = render_terminal([], {"clean": score})

    assert "Project Score:" not in output


def test_render_terminal_shows_top_findings_multi_module():
    d1 = _diag(module="mod_a", tier="P0", title="SQL injection in mod_a")
    d2 = _diag(module="mod_b", tier="P1", title="Missing access in mod_b")
    scores = {
        "mod_a": ScoreResult(50.0, "Needs work", [], [], 1),
        "mod_b": ScoreResult(70.0, "Needs work", [], [], 1),
    }
    output = render_terminal([d1, d2], scores)
    assert "Top Findings" in output
    assert "SQL injection in mod_a" in output


def test_render_terminal_no_top_findings_single_module():
    d1 = _diag(module="mod_a", tier="P0", title="SQL injection")
    scores = {"mod_a": ScoreResult(50.0, "Needs work", [], [], 1)}
    output = render_terminal([d1], scores)
    assert "Top Findings" not in output


def test_render_terminal_shows_one_decimal_score():
    score = ScoreResult(99.5, "Excellent", [], [], 0)
    output = render_terminal([], {"m": score})
    assert "99.5" in output
