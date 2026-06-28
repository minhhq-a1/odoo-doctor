# tests/core/test_scoring.py
"""Tests for the scoring engine."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import ScoreResult, score_diagnostics


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


def test_perfect_score_no_findings():
    result = score_diagnostics([], [])
    assert result.overall == 100.0
    assert result.label == "Excellent"


def test_single_p0_security():
    diags = [_diag(tier="P0", category="Security")]
    eligible = [True]
    result = score_diagnostics(diags, eligible, category_weights={"Security": 1.0})
    sec = next(c for c in result.categories if c.category == "Security")
    assert sec.score == 75  # 100 - 25
    assert sec.finding_count == 1


def test_ineligible_not_counted():
    diags = [_diag(tier="P0", category="Security", confidence="low")]
    eligible = [False]
    result = score_diagnostics(diags, eligible)
    sec = next(c for c in result.categories if c.category == "Security")
    assert sec.score == 100  # not counted


def test_category_weights_applied():
    diags = [_diag(tier="P1", category="Performance")]
    eligible = [True]
    result = score_diagnostics(diags, eligible, category_weights={"Performance": 2.0})
    perf = next(c for c in result.categories if c.category == "Performance")
    assert perf.score == 80  # 100 - (10 * 2.0)


def test_only_in_scope_categories_in_overall():
    """Empty categories (no active rules) should not inflate the overall score."""
    diags = [_diag(tier="P0", category="Security")]
    eligible = [True]
    in_scope = ["Security", "Correctness"]
    result = score_diagnostics(
        diags,
        eligible,
        category_weights={"Security": 1.0},
        in_scope_categories=in_scope,
    )
    # Security=75, Correctness=100 (no findings but in scope)
    # overall = 0.4 * min(75, 100) + 0.6 * avg(75, 100) = 30 + 52.5 = 82.5
    assert result.overall == 82.5
    assert result.in_scope_categories == ["Security", "Correctness"]


def test_blend_formula_punishes_weak_category():
    """A category at 0 should drag overall hard via 0.4*min."""
    diags = [
        _diag(tier="P0", category="Security"),
        _diag(tier="P0", category="Security", line=2),
        _diag(tier="P0", category="Security", line=3),
        _diag(tier="P0", category="Security", line=4),
    ]
    eligible = [True, True, True, True]
    in_scope = ["Security", "Correctness"]
    result = score_diagnostics(
        diags,
        eligible,
        category_weights={"Security": 1.0},
        in_scope_categories=in_scope,
    )
    # Security = max(0, 100 - 100) = 0, Correctness = 100
    # overall = 0.4 * 0 + 0.6 * 50 = 30.0
    assert result.overall == 30.0
    assert result.label == "Critical"


def test_labels():
    assert ScoreResult(95.0, "", [], [], 0).compute_label() == "Excellent"
    assert ScoreResult(80.0, "", [], [], 0).compute_label() == "Good"
    assert ScoreResult(60.0, "", [], [], 0).compute_label() == "Needs work"
    assert ScoreResult(30.0, "", [], [], 0).compute_label() == "Critical"


def test_score_overall_rounded_to_one_decimal():
    """A blend that yields 99.5142857… must be stored rounded to 1 decimal."""
    from odoo_doctor.core.diagnostics import CATEGORIES

    diags = [_diag(tier="P3", category="Security")]  # P3 impact = 1 → Security = 99
    eligible = [True]
    result = score_diagnostics(
        diags,
        eligible,
        category_weights={"Security": 1.0},
        in_scope_categories=list(CATEGORIES),
    )
    # min=99, avg=699/7=99.857…, overall=0.4*99 + 0.6*99.857… = 99.5142857…
    assert result.overall == 99.5


def test_default_category_weights_applied():
    """Default weights affect scoring when no user weights provided."""
    d = Diagnostic(
        module="mod",
        file_path="f.py",
        line=1,
        column=0,
        rule="r",
        category="Security",
        severity="error",
        tier="P1",
        source="native",
        confidence="high",
        title="t",
        message="m",
        help="h",
        odoo_version="17.0",
    )
    result = score_diagnostics([d], [True])
    # Security weight is 1.5, P1 impact is 10, so impact = 15
    sec = [c for c in result.categories if c.category == "Security"][0]
    assert sec.total_impact == 15.0


def test_user_weights_override_defaults():
    """User-provided weights override defaults."""
    d = Diagnostic(
        module="mod",
        file_path="f.py",
        line=1,
        column=0,
        rule="r",
        category="Security",
        severity="error",
        tier="P1",
        source="native",
        confidence="high",
        title="t",
        message="m",
        help="h",
        odoo_version="17.0",
    )
    result = score_diagnostics([d], [True], category_weights={"Security": 3.0})
    sec = [c for c in result.categories if c.category == "Security"][0]
    assert sec.total_impact == 30.0
