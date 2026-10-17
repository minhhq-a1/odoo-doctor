# src/odoo_doctor/core/scoring.py
"""Scoring engine — deterministic local health score."""

from __future__ import annotations

from dataclasses import dataclass, field

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT, Diagnostic

# Bumped whenever the scoring formula changes in a way that makes scores from
# different versions incomparable. 1 = <=0.3.0 (all weights 1.0), 2 = 0.4.0+
# (default per-category weights).
SCORE_SCHEMA_VERSION = 2

DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    "Security": 1.5,
    "Correctness": 1.5,
    "Performance": 1.0,
    "Data Integrity": 1.0,
    "Upgrade Safety": 1.0,
    "Module Hygiene": 0.8,
    "Maintainability": 0.5,
    "Frontend": 0.5,
}


@dataclass
class CategoryScore:
    category: str
    score: int  # 0–100
    finding_count: int
    total_impact: float


def score_label(overall: float) -> str:
    if overall >= 90:
        return "Excellent"
    if overall >= 75:
        return "Good"
    if overall >= 50:
        return "Needs work"
    return "Critical"


@dataclass
class ScoreResult:
    overall: float
    label: str
    categories: list[CategoryScore]
    in_scope_categories: list[str]
    diagnostics_counted: int
    # Best-first fix suggestions (core.roi.FixPriority); filled by the scanner.
    fix_priorities: list = field(default_factory=list)
    # Per-rule suppression counts for this module (core.suppression_stats):
    # {rule: {"surfaced", "inline", "ignore_rule", "severity_off"}}; filled by the scanner.
    suppression_stats: dict = field(default_factory=dict)
    # Same module score with `medium` findings counted too (None = not computed), and
    # the module's Python line count; both feed secondary_scores(), filled by the scanner.
    overall_with_medium: float | None = None
    python_lines: int = 0

    def compute_label(self) -> str:
        return score_label(self.overall)


def category_scores(
    impact: dict[str, float], counts: dict[str, int]
) -> list[CategoryScore]:
    """Per-category scores from accumulated (weighted) impact."""
    return [
        CategoryScore(
            category=cat,
            score=max(0, int(100 - impact[cat])),
            finding_count=counts[cat],
            total_impact=impact[cat],
        )
        for cat in CATEGORIES
    ]


def blend_overall(cat_scores: list[CategoryScore], scope: list[str]) -> float:
    """Overall score: blend over in-scope categories only."""
    in_scope_scores = [cs.score for cs in cat_scores if cs.category in scope]
    if not in_scope_scores:
        return 100.0
    overall = 0.4 * min(in_scope_scores) + 0.6 * (
        sum(in_scope_scores) / len(in_scope_scores)
    )
    return round(overall, 1)


def score_diagnostics(
    diagnostics: list[Diagnostic],
    eligible: list[bool],
    category_weights: dict[str, float] | None = None,
    in_scope_categories: list[str] | None = None,
) -> ScoreResult:
    """Compute per-category and overall health scores.

    Only diagnostics where eligible[i] is True are counted.
    Only in_scope_categories (those with >=1 active rule) affect the overall blend.
    """
    base_weights = dict(DEFAULT_CATEGORY_WEIGHTS)
    if category_weights:
        base_weights.update(category_weights)
    weights = base_weights
    scope = in_scope_categories if in_scope_categories is not None else list(CATEGORIES)

    # Accumulate impact per category
    impact: dict[str, float] = {cat: 0.0 for cat in CATEGORIES}
    counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    counted = 0

    for d, elig in zip(diagnostics, eligible):
        if not elig:
            continue
        if d.category not in impact:
            continue
        tier_pts = TIER_IMPACT.get(d.tier, 0)
        w = weights.get(d.category, 1.0)
        impact[d.category] += tier_pts * w
        counts[d.category] += 1
        counted += 1

    cat_scores = category_scores(impact, counts)
    overall = blend_overall(cat_scores, scope)

    result = ScoreResult(
        overall=overall,
        label="",
        categories=cat_scores,
        in_scope_categories=list(scope),
        diagnostics_counted=counted,
    )
    result.label = result.compute_label()
    return result


def project_score(scores: dict[str, ScoreResult]) -> dict[str, float | str | int]:
    """Aggregate module scores (plain mean) for project-level reporting."""
    module_count = len(scores)
    if module_count == 0:
        overall = 100.0
    else:
        overall = sum(score.overall for score in scores.values()) / module_count
    overall = round(overall, 1)
    return {
        "overall": overall,
        "label": score_label(overall),
        "module_count": module_count,
    }


def secondary_scores(scores: dict[str, ScoreResult]) -> dict[str, float]:
    """Extra project numbers shown next to the main score (which they never replace).

    ``weighted``: module scores averaged by Python line count (plain mean if no module
    has any lines). ``with_medium``: plain mean of the module scores that also count
    ``medium`` findings (a module without that number counts at its main score).
    """
    if not scores:
        return {"weighted": 100.0, "with_medium": 100.0}
    total = sum(s.python_lines for s in scores.values())
    if total > 0:
        weighted = sum(s.overall * s.python_lines for s in scores.values()) / total
    else:
        weighted = sum(s.overall for s in scores.values()) / len(scores)
    medium = sum(
        s.overall if s.overall_with_medium is None else s.overall_with_medium
        for s in scores.values()
    ) / len(scores)
    return {"weighted": round(weighted, 1), "with_medium": round(medium, 1)}
