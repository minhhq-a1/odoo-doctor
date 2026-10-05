# src/odoo_doctor/core/roi.py
"""Fix ROI ranking: which finding to fix first for the most score per unit of work.

``impact`` is what scoring deducts for the finding (tier points x category weight),
``effort`` is a coarse 1-3 estimate of the work to fix it, and ``roi`` is their
static ratio (informational).

Ranking is greedy on the *marginal overall-score gain per effort*, computed on
unclamped category scores. The overall blend is ``0.4*min + 0.6*avg``, so a point
recovered in the weakest category is worth far more than one elsewhere, and a
category already past 0 still needs its findings fixed before the real score moves.
``projected_score`` is the real (clamped) module score after fixing this finding
and every one ranked before it, and ``score_gain`` the real change this step made
(0.0 while a category is still saturated).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT, Diagnostic
from odoo_doctor.core.scoring import (
    DEFAULT_CATEGORY_WEIGHTS,
    blend_overall,
    category_scores,
)

DEFAULT_EFFORT = 2

# 1 = mechanical (a missing key, comment, argument or reference), 2 = a local code
# change that needs a little thought, 3 = restructuring (batching, redesigning
# access). Every native rule must have an entry (enforced by a test).
EFFORT_BY_RULE: dict[str, int] = {
    # 1: mechanical
    "manifest-missing-required-fields": 1,
    "manifest-data-order-risk": 1,
    "manifest-missing-dependency": 1,
    "missing-access-csv": 1,
    "unknown-model-in-access-csv": 1,
    "sudo-without-comment": 1,
    "duplicate-xml-id": 1,
    "compute-missing-depends": 1,
    "field-no-string-on-required": 1,
    "missing-translation": 1,
    "monetary-missing-currency-field": 1,
    "missing-ondelete": 1,
    "data-noupdate-risk": 1,
    "orphan-view": 1,
    "asset-bundle-missing": 1,
    # 2: local code change
    "raw-sql-string-interpolation": 2,
    "eval-usage": 2,
    "record-rule-without-domain": 2,
    "missing-multicompany-rule": 2,
    "hardcoded-company-or-currency": 2,
    "missing-xml-ref": 2,
    "view-field-not-in-model": 2,
    "button-method-not-found": 2,
    "override-missing-super": 2,
    "unbounded-search": 2,
    "expensive-nonstored-compute": 2,
    "deprecated-api-usage": 2,
    "removed-model-still-referenced": 2,
    # 3: restructuring
    "public-controller-sudo-risk": 3,
    "search-in-loop": 3,
    "create-in-loop": 3,
    "write-in-loop": 3,
    "n-plus-one-read": 3,
}


@dataclass(frozen=True)
class FixPriority:
    rule: str
    file_path: str
    line: int
    tier: str
    category: str
    title: str
    impact: float
    effort: int
    roi: float
    projected_score: float
    score_gain: float
    fixable: bool


def _virtual_overall(raw: dict[str, float], scope: list[str]) -> float:
    """Unclamped, unrounded blend used only to order fixes."""
    values = [raw[c] for c in scope if c in raw]
    if not values:
        return 100.0
    return 0.4 * min(values) + 0.6 * (sum(values) / len(values))


def rank_fixes(
    diagnostics: list[Diagnostic],
    eligible: list[bool],
    category_weights: dict[str, float] | None,
    in_scope_categories: list[str] | None,
    is_fixable: Callable[[str], bool],
) -> list[FixPriority]:
    """Rank score-eligible findings, best next fix first."""
    weights = {**DEFAULT_CATEGORY_WEIGHTS, **(category_weights or {})}
    scope = in_scope_categories if in_scope_categories is not None else list(CATEGORIES)

    def order(e: tuple[Diagnostic, float, int, bool]):
        d, points, effort, _ = e
        return (-(points / effort), d.tier, d.file_path, d.line, d.rule)

    pending: dict[str, list[tuple[Diagnostic, float, int, bool]]] = {
        cat: [] for cat in CATEGORIES
    }
    impact: dict[str, float] = {cat: 0.0 for cat in CATEGORIES}
    counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    for d, ok in zip(diagnostics, eligible):
        if not ok or d.category not in impact:
            continue
        points = TIER_IMPACT.get(d.tier, 0) * weights.get(d.category, 1.0)
        fixable = is_fixable(d.rule)
        effort = 1 if fixable else EFFORT_BY_RULE.get(d.rule, DEFAULT_EFFORT)
        pending[d.category].append((d, points, effort, fixable))
        impact[d.category] += points
        counts[d.category] += 1
    for entries in pending.values():
        entries.sort(key=order)

    raw = {cat: 100.0 - impact[cat] for cat in CATEGORIES}
    previous = blend_overall(category_scores(impact, counts), scope)
    ranked: list[FixPriority] = []

    def take(cat: str) -> None:
        nonlocal previous
        d, points, effort, fixable = pending[cat].pop(0)
        raw[cat] += points
        impact[cat] -= points
        counts[cat] -= 1
        projected = blend_overall(category_scores(impact, counts), scope)
        ranked.append(
            FixPriority(
                rule=d.rule,
                file_path=d.file_path,
                line=d.line,
                tier=d.tier,
                category=d.category,
                title=d.title,
                impact=points,
                effort=effort,
                roi=points / effort,
                projected_score=projected,
                score_gain=round(projected - previous, 1),
                fixable=fixable,
            )
        )
        previous = projected

    in_scope = [c for c in CATEGORIES if c in scope]
    while any(pending[c] for c in in_scope):
        current = _virtual_overall(raw, scope)
        best: tuple | None = None
        for cat in in_scope:
            if not pending[cat]:
                continue
            entry = pending[cat][0]
            _, points, effort, _ = entry
            trial = dict(raw)
            trial[cat] += points
            gain = _virtual_overall(trial, scope) - current
            key = (-(gain / effort), *order(entry))
            if best is None or key < best[0]:
                best = (key, cat)
        assert best is not None
        take(best[1])

    # Findings in categories outside the scoring scope cannot move the score;
    # list them last, by static ROI.
    for cat in CATEGORIES:
        while pending[cat]:
            take(cat)
    return ranked
