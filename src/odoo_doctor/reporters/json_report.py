# src/odoo_doctor/reporters/json_report.py
"""JSON reporter — stable schema for agents and CI."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

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

    return json.dumps({"version": "0.1.0", "modules": modules}, indent=2)
