"""Upgrade readiness report: classification table, readiness formula, report shape."""

from __future__ import annotations

import odoo_doctor.cli.app  # noqa: F401  (registers every rule)
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.roi import EFFORT_BY_RULE
from odoo_doctor.core.upgrade import (
    MECHANICAL_RENAMES,
    MECHANICAL_RULES,
    READINESS_SCHEMA_VERSION,
    RULE_GROUPS,
    build_upgrade_report,
    has_migration_rules,
    readiness_score,
    render_upgrade_report,
)
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.upgrade_safety.removed_core_field_usage import _REMOVED_FIELDS


def _diag(
    rule="view-tree-removed",
    *,
    module="m",
    file="a.xml",
    confidence="high",
    tier="P1",
    title="t",
    category="Upgrade Safety",
) -> Diagnostic:
    return Diagnostic(
        module=module,
        file_path=file,
        line=1,
        column=0,
        rule=rule,
        category=category,
        severity="error",
        tier=tier,
        source="native",
        confidence=confidence,
        title=title,
        message="m",
        help="h",
        odoo_version="19.0",
    )


def _field(model, field, confidence="high"):
    return _diag(
        "removed-core-field-usage",
        confidence=confidence,
        title=f"'{field}' no longer exists on {model} (Odoo 19)",
    )


def _only_group(report, module="m"):
    (group,) = report["modules"][module]["groups"]
    return group


def test_every_upgrade_safety_rule_has_a_group():
    names = {
        meta.name
        for meta, _ in default_registry.get_rules()
        if meta.category == "Upgrade Safety"
    }
    assert names <= set(RULE_GROUPS), sorted(names - set(RULE_GROUPS))
    assert set(RULE_GROUPS) <= names, "stale rule in the table"
    assert set(RULE_GROUPS) <= set(EFFORT_BY_RULE)


def test_mechanical_table_matches_the_rules_own_tables():
    for (model, field), new in MECHANICAL_RENAMES.items():
        assert _REMOVED_FIELDS[model][field][1] == new, (model, field)
    assert MECHANICAL_RULES <= set(RULE_GROUPS)


def test_high_finding_of_a_mechanical_rule_is_mechanical():
    report = build_upgrade_report([_diag("view-tree-removed")], ["m"], "19.0")
    group = _only_group(report)
    assert (group["mechanical"], group["needs_review"]) == (1, 0)


def test_medium_finding_is_never_mechanical():
    for rule in MECHANICAL_RULES:
        report = build_upgrade_report([_diag(rule, confidence="medium")], ["m"], "19.0")
        assert _only_group(report)["mechanical"] == 0, rule
    report = build_upgrade_report(
        [_field("res.users", "groups_id", "medium")], ["m"], "19.0"
    )
    assert _only_group(report)["needs_review"] == 1


def test_rule_outside_the_table_is_needs_review():
    report = build_upgrade_report([_diag("kanban-legacy-templates")], ["m"], "19.0")
    assert _only_group(report)["needs_review"] == 1


def test_removed_field_entries_decide_individually():
    mech = [_field("res.users", "groups_id"), _field("res.groups", "users")]
    review = [
        _field("res.groups", "category_id"),
        _field("account.account", "deprecated"),
        _field("res.partner", "mobile"),
        _field("ir.filters", "user_id"),
        _field("product.template", "detailed_type"),
    ]
    report = build_upgrade_report(mech + review, ["m"], "19.0")
    group = _only_group(report)
    assert (group["findings"], group["mechanical"], group["needs_review"]) == (7, 2, 5)


def test_readiness_formula_hand_computed():
    assert readiness_score([]) == 100.0
    # one P1: 100 * 100 / (100 + 10)
    assert readiness_score([_diag()]) == 90.9
    # two P1 + one P2 = 24 points: 100 * 100 / 124
    assert readiness_score([_diag(), _diag(), _diag(tier="P2")]) == 80.6
    # only high findings count
    assert (
        readiness_score([_diag(confidence="medium"), _diag(confidence="low")]) == 100.0
    )


def test_readiness_counts_only_upgrade_safety():
    assert readiness_score([_diag(category="Security", tier="P0")]) == 100.0


def test_report_shape_groups_files_and_effort():
    diags = [
        _diag("view-tree-removed", file="a.xml"),
        _diag("view-tree-removed", file="a.xml"),
        _diag("view-tree-removed", file="b.xml", confidence="medium"),
        _diag("removed-orm-api-usage", file="p.py"),
        _diag("removed-model-still-referenced", file="q.py", confidence="medium"),
    ]
    report = build_upgrade_report(diags, ["m", "clean"], "19.0")
    assert report["readiness_schema_version"] == READINESS_SCHEMA_VERSION == 1
    assert report["target_version"] == "19.0"
    assert report["modules"]["clean"]["score"] == 100.0
    assert report["modules"]["clean"]["groups"] == []
    m = report["modules"]["m"]
    tree, apis = m["groups"]
    assert tree["rules"] == ["view-tree-removed"]
    assert (tree["findings"], tree["files"]) == (3, 2)
    assert tree["effort"] == 3 * EFFORT_BY_RULE["view-tree-removed"]
    assert (tree["mechanical"], tree["needs_review"]) == (2, 1)
    assert apis["rules"] == ["removed-model-still-referenced", "removed-orm-api-usage"]
    assert apis["findings"] == 2
    totals = m["totals"]
    assert totals["findings"] == 5 and totals["files"] == 4
    assert totals["mechanical"] + totals["needs_review"] == totals["findings"]
    assert report["totals"]["findings"] == 5
    assert report["totals"]["modules"] == 2


def test_modules_found_only_in_diagnostics_are_kept():
    report = build_upgrade_report([_diag(module="other")], ["m"], "19.0")
    assert set(report["modules"]) == {"m", "other"}


def test_other_categories_are_not_counted():
    report = build_upgrade_report([_diag(category="Security")], ["m"], "19.0")
    assert report["totals"]["findings"] == 0


def test_has_migration_rules():
    assert has_migration_rules("19.0") and has_migration_rules("18.0")
    assert not has_migration_rules("17.0")
    assert not has_migration_rules("unknown")


def test_text_render():
    diags = [_diag(), _diag(confidence="medium")]
    text = render_upgrade_report(build_upgrade_report(diags, ["m", "clean"], "19.0"))
    assert "19.0" in text and "m" in text
    assert "1 mechanical" in text and "1 need review" in text
    assert "fixer planned" in text
    assert "no Upgrade Safety findings" in text
    assert "auto-fix" not in text
