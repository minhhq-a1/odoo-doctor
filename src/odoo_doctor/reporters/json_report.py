# src/odoo_doctor/reporters/json_report.py
"""JSON reporter — stable schema for agents and CI."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

import odoo_doctor.rules.manifest.data_order_risk

# Importing the rule modules triggers their @rule registration so the registry
# knows their fixable flag. Import only what this reporter needs.
import odoo_doctor.rules.manifest.missing_required_fields  # noqa: F401
from odoo_doctor import __version__
from odoo_doctor.core.scoring import SCORE_SCHEMA_VERSION, project_score
from odoo_doctor.rules.registry import default_registry

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
            "version": __version__,
            "schema_version": "1.0",
            "score_schema_version": SCORE_SCHEMA_VERSION,
            "project_score": project_score(scores),
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
                    "fixable": _is_fixable(d.rule),
                }
                for d in top
            ],
            "modules": modules,
        },
        indent=2,
    )


def _is_fixable(rule_name: str) -> bool:
    entry = default_registry.get(rule_name)
    return bool(entry and entry[0].fixable)
