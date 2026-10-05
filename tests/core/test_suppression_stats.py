"""Suppression analytics: counting and noise logic (pure, no scan)."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.suppression_stats import (
    RuleNoise,
    actionable_count,
    build_stats,
    rule_noise,
)


def _diag(module: str = "m", rule: str = "r") -> Diagnostic:
    return Diagnostic(
        module=module,
        file_path="f.py",
        line=1,
        column=0,
        rule=rule,
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="h",
        odoo_version="17.0",
    )


def _counts(**kw: int) -> dict[str, int]:
    return {"surfaced": 0, "inline": 0, "ignore_rule": 0, "severity_off": 0, **kw}


def test_build_stats_counts_each_channel():
    stats = build_stats(
        [_diag(rule="a")],
        {
            "inline": [_diag(rule="a"), _diag(rule="a")],
            "ignore_rule": [_diag(rule="b")],
            "severity_off": [],
        },
    )
    assert stats == {
        "m": {
            "a": _counts(surfaced=1, inline=2),
            "b": _counts(ignore_rule=1),
        }
    }


def test_build_stats_groups_by_module():
    stats = build_stats([_diag(module="m1"), _diag(module="m2")], {})
    assert stats == {
        "m1": {"r": _counts(surfaced=1)},
        "m2": {"r": _counts(surfaced=1)},
    }


def test_below_min_sample_is_not_noisy():
    assert not RuleNoise("r", surfaced=1, inline=8, ignore_rule=0, severity_off=0).noisy


def test_at_min_sample_and_ratio_is_noisy():
    row = RuleNoise("r", surfaced=5, inline=5, ignore_rule=0, severity_off=0)
    assert row.total == 10
    assert row.ratio == 0.5
    assert row.noisy


def test_below_ratio_is_not_noisy():
    assert not RuleNoise("r", surfaced=6, inline=4, ignore_rule=0, severity_off=0).noisy


def test_zero_total_is_safe():
    row = RuleNoise("r", surfaced=0, inline=0, ignore_rule=0, severity_off=0)
    assert row.ratio == 0.0
    assert not row.noisy
    assert row.suggestion is None


def test_suggestion_when_mostly_inline():
    row = RuleNoise("r", surfaced=1, inline=8, ignore_rule=1, severity_off=0)
    assert row.noisy
    assert '"r"' in row.suggestion
    assert "info" in row.suggestion
    assert "[severity]" in row.suggestion


def test_no_suggestion_when_rule_is_disabled_in_config():
    row = RuleNoise("r", surfaced=0, inline=0, ignore_rule=12, severity_off=0)
    assert row.noisy
    assert row.suggestion is None


def test_no_suggestion_when_inline_is_not_the_main_channel():
    row = RuleNoise("r", surfaced=1, inline=3, ignore_rule=3, severity_off=3)
    assert row.noisy
    assert row.suggestion is None


def test_rule_noise_aggregates_modules_and_sorts_noisiest_first():
    stats = {
        "m1": {"a": _counts(surfaced=1, inline=4)},
        "m2": {"a": _counts(surfaced=1, inline=4), "b": _counts(surfaced=5)},
    }
    rows = rule_noise(stats)
    assert [r.rule for r in rows] == ["a", "b"]
    assert (rows[0].surfaced, rows[0].inline) == (2, 8)
    assert rows[1].ratio == 0.0


def test_actionable_count_counts_only_rules_with_a_suggestion():
    stats = {
        "m": {
            "inline_noisy": _counts(surfaced=1, inline=9),
            "disabled": _counts(ignore_rule=12),
            "quiet": _counts(surfaced=3),
        }
    }
    assert actionable_count(stats) == 1
