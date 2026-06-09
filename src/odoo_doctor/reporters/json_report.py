# src/odoo_doctor/reporters/json_report.py
"""JSON reporter — stable schema for agents and CI."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from odoo_doctor.core.scoring import score_label

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


def render_json(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
) -> str:
    """Render scan results as JSON."""
    by_module: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_module.setdefault(d.module, []).append(d)

    modules: dict[str, dict] = {}
    for module_name, score in scores.items():
        module_diags = by_module.get(module_name, [])
        modules[module_name] = {
            "score": {
                "overall": score.overall,
                "label": score.label,
                "categories": [
                    {
                        "category": cs.category,
                        "score": cs.score,
                        "finding_count": cs.finding_count,
                    }
                    for cs in score.categories
                    if cs.category in score.in_scope_categories
                ],
                "diagnostics_counted": score.diagnostics_counted,
            },
            "diagnostics": [asdict(d) for d in module_diags],
        }

    top = sorted(diagnostics, key=lambda d: (d.tier, d.file_path, d.line))[:5]

    # Using version tracking for tooling compatibility
    return json.dumps(
        {
            "version": "0.2.0",
            "schema_version": "1.0",
            "project_score": _project_score(scores),
            "top_findings": [
                {
                    "module": d.module,
                    "file_path": d.file_path,
                    "line": d.line,
                    "rule": d.rule,
                    "tier": d.tier,
                    "title": d.title,
                    "category": d.category,
                    "severity": d.severity,
                    "confidence": d.confidence,
                }
                for d in top
            ],
            "modules": modules,
        },
        indent=2,
    )


def _project_score(scores: dict[str, ScoreResult]) -> dict[str, float | str | int]:
    """Aggregate module scores for project-level reporting."""
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
