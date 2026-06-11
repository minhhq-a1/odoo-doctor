# src/odoo_doctor/reporters/sarif.py
"""SARIF 2.1.0 reporter for GitHub Code Scanning and IDE integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic

_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

# Odoo Doctor severity -> SARIF level.
_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


def _rel(path: str, base_path: Path | None) -> str:
    norm = path.replace("\\", "/")
    if base_path is not None:
        try:
            return Path(norm).resolve().relative_to(Path(base_path).resolve()).as_posix()
        except ValueError:
            return norm
    return norm


def render_sarif(diagnostics: list[Diagnostic], base_path: Path | None) -> str:
    # Deduplicate rule descriptors by ruleId.
    rules_by_id: dict[str, dict] = {}
    results: list[dict] = []

    for d in diagnostics:
        if d.rule not in rules_by_id:
            rules_by_id[d.rule] = {
                "id": d.rule,
                "name": d.rule,
                "shortDescription": {"text": d.title},
                "fullDescription": {"text": d.help or d.title},
                "defaultConfiguration": {"level": _LEVEL.get(d.severity, "warning")},
                "properties": {"category": d.category, "tier": d.tier},
            }
        results.append(
            {
                "ruleId": d.rule,
                "level": _LEVEL.get(d.severity, "warning"),
                "message": {"text": d.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": _rel(d.file_path, base_path)
                            },
                            "region": {
                                "startLine": max(1, d.line),
                                "startColumn": max(1, d.column + 1),
                            },
                        }
                    }
                ],
                "properties": {
                    "confidence": d.confidence,
                    "tier": d.tier,
                    "category": d.category,
                    "module": d.module,
                },
            }
        )

    log = {
        "$schema": _SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "odoo-doctor",
                        "informationUri": "https://github.com/minhhq-a1/odoo-doctor",
                        "rules": list(rules_by_id.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2)
