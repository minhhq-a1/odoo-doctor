# src/odoo_doctor/reporters/rule_stats.py
"""Reporters for ``odoo-doctor rules stats``."""

from __future__ import annotations

import json
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from odoo_doctor.core.suppression_stats import MIN_SAMPLE, NOISY_RATIO

if TYPE_CHECKING:
    from odoo_doctor.core.suppression_stats import RuleNoise


def render_rule_stats_json(rows: list[RuleNoise]) -> str:
    return json.dumps(
        {
            "thresholds": {"min_sample": MIN_SAMPLE, "noisy_ratio": NOISY_RATIO},
            "rules": [
                {
                    "rule": r.rule,
                    "surfaced": r.surfaced,
                    "inline": r.inline,
                    "ignore_rule": r.ignore_rule,
                    "severity_off": r.severity_off,
                    "suppressed": r.suppressed,
                    "total": r.total,
                    "ratio": round(r.ratio, 3),
                    "noisy": r.noisy,
                    "suggestion": r.suggestion,
                }
                for r in rows
            ],
        },
        indent=2,
    )


def render_rule_stats(rows: list[RuleNoise]) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)
    if not rows:
        console.print("No findings or suppressions recorded.")
        return buf.getvalue()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Rule")
    for name in ("Surfaced", "Inline", "Ignored", "Off", "Noise"):
        table.add_column(name, justify="right")
    table.add_column("")
    for r in rows:
        table.add_row(
            r.rule,
            str(r.surfaced),
            str(r.inline),
            str(r.ignore_rule),
            str(r.severity_off),
            f"{r.ratio:.0%}",
            "[red]noisy[/red]" if r.noisy else "",
        )
    console.print(table)
    console.print(
        "Inline = # odoo-doctor: disable, Ignored = [ignore] rules, "
        "Off = [severity] off. A finding counts once, in the first channel "
        "that drops it (Off, then Ignored, then Inline).",
        markup=False,
        highlight=False,
    )
    for r in rows:
        if r.suggestion:
            console.print(f"  - {r.suggestion}", markup=False, highlight=False)
    return buf.getvalue()
