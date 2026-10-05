"""Fix ROI ranking: which finding to fix first for the biggest score gain per effort."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import odoo_doctor.cli.app  # noqa: F401  (registers all built-in rules)
from odoo_doctor.cli.app import app
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.roi import EFFORT_BY_RULE, rank_fixes
from odoo_doctor.core.scoring import score_diagnostics
from odoo_doctor.rules.registry import default_registry


def _diag(
    rule: str,
    *,
    tier: str = "P1",
    category: str = "Correctness",
    file_path: str = "m/a.py",
    line: int = 1,
) -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path=file_path,
        line=line,
        column=0,
        rule=rule,
        category=category,
        severity="error",
        tier=tier,
        source="native",
        confidence="high",
        title=rule,
        message="",
        help="",
        odoo_version="17.0",
    )


def _rank(diags, eligible=None, fixable=()):
    eligible = [True] * len(diags) if eligible is None else eligible
    return rank_fixes(
        diags,
        eligible,
        category_weights=None,
        in_scope_categories=None,
        is_fixable=lambda rule: rule in fixable,
    )


def test_every_native_rule_has_an_explicit_effort():
    names = {meta.name for meta, _ in default_registry.get_rules()}
    assert names - set(EFFORT_BY_RULE) == set(), "rules missing from roi.EFFORT_BY_RULE"
    assert set(EFFORT_BY_RULE) - names == set(), "stale entries in roi.EFFORT_BY_RULE"
    assert set(EFFORT_BY_RULE.values()) <= {1, 2, 3}


def test_higher_impact_per_effort_comes_first():
    cheap_big = _diag("raw-sql-string-interpolation", tier="P0", category="Security")
    cheap_small = _diag("orphan-view", tier="P2", category="Maintainability")
    ranked = _rank([cheap_small, cheap_big])
    assert [r.rule for r in ranked] == ["raw-sql-string-interpolation", "orphan-view"]


def test_lower_effort_beats_equal_impact():
    easy = _diag("missing-ondelete", tier="P1", category="Data Integrity")
    hard = _diag("search-in-loop", tier="P1", category="Data Integrity")
    assert EFFORT_BY_RULE["missing-ondelete"] < EFFORT_BY_RULE["search-in-loop"]
    ranked = _rank([hard, easy])
    assert ranked[0].rule == "missing-ondelete"


def test_fixable_rules_have_minimal_effort():
    d = _diag("n-plus-one-read", tier="P1", category="Performance")
    assert _rank([d])[0].effort == EFFORT_BY_RULE["n-plus-one-read"]
    assert _rank([d], fixable={"n-plus-one-read"})[0].effort == 1


def test_unknown_rule_gets_default_effort():
    assert _rank([_diag("ruff:E501")])[0].effort == 2


def test_ineligible_findings_are_not_ranked():
    diags = [_diag("eval-usage", tier="P0"), _diag("orphan-view", tier="P2")]
    ranked = _rank(diags, eligible=[False, True])
    assert [r.rule for r in ranked] == ["orphan-view"]


def test_roi_is_impact_over_effort():
    d = _diag("raw-sql-string-interpolation", tier="P0", category="Security")
    r = _rank([d])[0]
    assert r.impact == 25 * 1.5
    assert r.roi == r.impact / r.effort


def test_projected_score_matches_a_real_rescore():
    diags = [
        _diag("raw-sql-string-interpolation", tier="P0", category="Security", line=1),
        _diag("missing-ondelete", tier="P1", category="Data Integrity", line=2),
        _diag("orphan-view", tier="P2", category="Maintainability", line=3),
    ]
    ranked = _rank(diags)
    remaining = list(diags)
    for r in ranked:
        remaining = [d for d in remaining if (d.rule, d.line) != (r.rule, r.line)]
        expected = score_diagnostics(remaining, [True] * len(remaining)).overall
        assert r.projected_score == expected


def test_projected_score_never_decreases_and_ends_at_100_when_all_fixed():
    diags = [
        _diag("eval-usage", tier="P0", category="Security", line=i) for i in (1, 2)
    ]
    scores = [r.projected_score for r in _rank(diags)]
    assert scores == sorted(scores)
    assert scores[-1] == 100.0


def test_ranking_is_deterministic_on_ties():
    a = _diag("orphan-view", tier="P2", category="Maintainability", file_path="m/b.xml")
    b = _diag("orphan-view", tier="P2", category="Maintainability", file_path="m/a.xml")
    assert [r.file_path for r in _rank([a, b])] == ["m/a.xml", "m/b.xml"]
    assert [r.file_path for r in _rank([b, a])] == ["m/a.xml", "m/b.xml"]


def test_weakest_category_is_attacked_first():
    # Data Integrity is far past saturation (12 P1 findings => raw score -20). The
    # overall blend is 0.4*min + 0.6*avg, so one of its findings (+4.75 overall)
    # beats a P0 Security finding (+2.8) even though the Security finding has the
    # higher static impact/effort (37.5 vs 10).
    di = [
        _diag("missing-ondelete", tier="P1", category="Data Integrity", line=i)
        for i in range(1, 13)
    ]
    sec = _diag("missing-access-csv", tier="P0", category="Security", line=0)
    assert EFFORT_BY_RULE["missing-access-csv"] == EFFORT_BY_RULE["missing-ondelete"]
    ranked = _rank([sec, *di])
    assert ranked[0].rule == "missing-ondelete"


def test_score_gain_accounts_for_every_point_recovered():
    diags = [
        _diag("missing-ondelete", tier="P1", category="Data Integrity", line=i)
        for i in range(12)
    ] + [_diag("orphan-view", tier="P2", category="Maintainability", line=99)]
    ranked = _rank(diags)
    base = score_diagnostics(diags, [True] * len(diags)).overall
    assert ranked[0].score_gain == 0.0  # still saturated after the first fix
    assert round(sum(r.score_gain for r in ranked), 1) == round(100.0 - base, 1)
    assert all(r.score_gain >= 0 for r in ranked)


def test_no_findings_means_empty_ranking():
    assert _rank([]) == []


# --- surfaced in the reports --------------------------------------------------


def _scan_json(tmp_path: Path) -> dict:
    mod = tmp_path / "mod"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    (mod / "models" / "m.py").write_text(
        "from odoo import models, fields\n\n"
        "class M(models.Model):\n"
        "    _name = 'mod.m'\n"
        "    _description = 'M'\n"
        "    partner_id = fields.Many2one('res.partner')\n\n"
        "    def run(self, name):\n"
        "        self.env.cr.execute(f\"SELECT 1 FROM t WHERE n = '{name}'\")\n"
    )
    result = CliRunner().invoke(app, ["scan", str(tmp_path), "--json"])
    return json.loads(result.stdout)


def test_json_report_has_fix_priorities_per_module(tmp_path: Path):
    report = _scan_json(tmp_path)
    priorities = report["modules"]["mod"]["fix_priorities"]
    assert priorities, "expected at least one prioritized fix"
    first = priorities[0]
    assert set(first) >= {
        "rank",
        "rule",
        "file_path",
        "line",
        "tier",
        "impact",
        "effort",
        "roi",
        "projected_score",
        "score_gain",
        "fixable",
    }
    assert [p["rank"] for p in priorities] == list(range(1, len(priorities) + 1))
    assert len(priorities) <= 10


def test_terminal_report_lists_fix_first(tmp_path: Path):
    _scan_json(tmp_path)  # builds the addon
    result = CliRunner().invoke(app, ["scan", str(tmp_path)])
    assert "Fix first" in result.stdout
