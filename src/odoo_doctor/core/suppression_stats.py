# src/odoo_doctor/core/suppression_stats.py
"""Suppression analytics: which rules do users switch off, and how often.

Pure helpers over the per-module counts the pipeline produces
(``pipeline.run_pipeline_with_stats``). Three channels count as a "this rule is noisy"
signal: inline ``# odoo-doctor: disable``, ``[ignore] rules`` and
``[severity] = "off"``. ``[ignore] files/modules`` (scope exclusion) and the baseline
(existing debt) are deliberately not counted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic

# Order = the order the pipeline stages run; a finding counts in the first that drops it.
CHANNELS: tuple[str, ...] = ("inline", "ignore_rule", "severity_off")

# Tunable and chosen without real-world data: a rule needs this many findings
# (surfaced + suppressed) before its ratio means anything.
MIN_SAMPLE = 10
NOISY_RATIO = 0.5

# {module: {rule: {"surfaced": n, "inline": n, "ignore_rule": n, "severity_off": n}}}
SuppressionStats = dict[str, dict[str, dict[str, int]]]


def build_stats(
    surfaced: Iterable[Diagnostic],
    dropped: dict[str, Iterable[Diagnostic]],
) -> SuppressionStats:
    """Count surviving findings and the findings dropped by each channel."""
    stats: SuppressionStats = {}

    def bucket(d: Diagnostic) -> dict[str, int]:
        counts = {"surfaced": 0, **{channel: 0 for channel in CHANNELS}}
        return stats.setdefault(d.module, {}).setdefault(d.rule, counts)

    for d in surfaced:
        bucket(d)["surfaced"] += 1
    for channel, diagnostics in dropped.items():
        for d in diagnostics:
            bucket(d)[channel] += 1
    return stats


@dataclass(frozen=True)
class RuleNoise:
    """One rule's counts across the whole project, plus the derived noise verdict."""

    rule: str
    surfaced: int
    inline: int
    ignore_rule: int
    severity_off: int

    @property
    def suppressed(self) -> int:
        return self.inline + self.ignore_rule + self.severity_off

    @property
    def total(self) -> int:
        return self.surfaced + self.suppressed

    @property
    def ratio(self) -> float:
        return self.suppressed / self.total if self.total else 0.0

    @property
    def noisy(self) -> bool:
        return self.total >= MIN_SAMPLE and self.ratio >= NOISY_RATIO

    @property
    def suggestion(self) -> str | None:
        """Only for rules users silence one comment at a time.

        A rule already disabled through config needs no advice: the user decided.
        """
        if self.noisy and self.inline > self.ignore_rule + self.severity_off:
            return (
                f'consider setting "{self.rule}" = "info" under [severity] '
                "in odoo-doctor.toml"
            )
        return None


def rule_noise(stats: SuppressionStats) -> list[RuleNoise]:
    """Aggregate across modules; noisiest first, then largest, then by name."""
    totals: dict[str, dict[str, int]] = {}
    for rules in stats.values():
        for rule, counts in rules.items():
            acc = totals.setdefault(
                rule, {"surfaced": 0, **{channel: 0 for channel in CHANNELS}}
            )
            for key, value in counts.items():
                acc[key] = acc.get(key, 0) + value
    rows = [
        RuleNoise(
            rule=rule,
            surfaced=acc["surfaced"],
            inline=acc["inline"],
            ignore_rule=acc["ignore_rule"],
            severity_off=acc["severity_off"],
        )
        for rule, acc in totals.items()
    ]
    return sorted(rows, key=lambda r: (-r.ratio, -r.total, r.rule))


def actionable_count(stats: SuppressionStats) -> int:
    """How many rules are noisy AND have advice to give (drives the scan hint)."""
    return sum(1 for row in rule_noise(stats) if row.suggestion is not None)
