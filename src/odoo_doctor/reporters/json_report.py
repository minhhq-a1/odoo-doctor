# src/odoo_doctor/reporters/json_report.py
"""JSON reporter — stable schema for agents and CI."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from odoo_doctor import __version__
from odoo_doctor.core.scoring import (
    SCORE_SCHEMA_VERSION,
    project_score,
    secondary_scores,
)
from odoo_doctor.rules.registry import default_registry

# Importing the rule modules triggers their @rule registration so the registry
# knows their fixable flag. Import only what this reporter needs. Registration order is
# import order (it decides the order of `rules list`), so keep these two as they are.
# isort: off
import odoo_doctor.rules.manifest.missing_required_fields
import odoo_doctor.rules.manifest.data_order_risk
# isort: on

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


# How many ranked fixes each module reports (the full ranking can be thousands).
_MAX_FIX_PRIORITIES = 10


def build_payload(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
) -> dict:
    """Build the scan result as a plain dict (the content of ``scan --json``)."""
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
            "fix_priorities": [
                {"rank": rank, **asdict(fp)}
                for rank, fp in enumerate(score.fix_priorities[:_MAX_FIX_PRIORITIES], 1)
            ],
            "suppression_stats": getattr(score, "suppression_stats", {}),
            "diagnostics": [asdict(d) for d in module_diags],
        }

    top = sorted(diagnostics, key=lambda d: (d.tier, d.file_path, d.line))[:5]

    # Using version tracking for tooling compatibility
    return {
        "version": __version__,
        "schema_version": "1.0",
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "project_score": {**project_score(scores), **secondary_scores(scores)},
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
    }


def render_json(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
    upgrade_report: dict | None = None,
) -> str:
    """Render scan results as JSON; ``upgrade_report`` adds the top-level key of that name."""
    payload = build_payload(diagnostics, scores)
    if upgrade_report is not None:
        payload["upgrade_report"] = upgrade_report
    return json.dumps(payload, indent=2)


def _is_fixable(rule_name: str) -> bool:
    entry = default_registry.get(rule_name)
    return bool(entry and entry[0].fixable)
