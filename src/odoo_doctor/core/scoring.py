# src/odoo_doctor/core/scoring.py
"""Scoring engine — deterministic local health score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT, Diagnostic

if TYPE_CHECKING:
    pass


@dataclass
class CategoryScore:
    category: str
    score: int          # 0–100
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

    def compute_label(self) -> str:
        return score_label(self.overall)


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
    weights = category_weights or {}
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

    # Build category scores
    cat_scores: list[CategoryScore] = []
    for cat in CATEGORIES:
        score = max(0, int(100 - impact[cat]))
        cat_scores.append(CategoryScore(
            category=cat,
            score=score,
            finding_count=counts[cat],
            total_impact=impact[cat],
        ))

    # Overall: blend over in-scope categories only
    in_scope_scores = [cs.score for cs in cat_scores if cs.category in scope]
    if not in_scope_scores:
        overall = 100.0
    else:
        overall = 0.4 * min(in_scope_scores) + 0.6 * (sum(in_scope_scores) / len(in_scope_scores))
    overall = round(overall, 1)

    result = ScoreResult(
        overall=overall,
        label="",
        categories=cat_scores,
        in_scope_categories=list(scope),
        diagnostics_counted=counted,
    )
    result.label = result.compute_label()
    return result
