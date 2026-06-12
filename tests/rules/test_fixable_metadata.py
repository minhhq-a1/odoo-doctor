"""Rules can declare fixable=True via the @rule decorator."""

from __future__ import annotations

from odoo_doctor.rules.registry import RuleRegistry, rule


def test_rule_meta_defaults_to_not_fixable():
    reg = RuleRegistry()

    @rule(
        name="x-rule",
        category="Module Hygiene",
        tier="P2",
        severity="warning",
        default_confidence="high",
        needs_context=True,
        registry=reg,
    )
    def _x(ctx):  # pragma: no cover - registration only
        return []

    meta, _ = reg.get("x-rule")
    assert meta.fixable is False


def test_rule_meta_can_be_marked_fixable():
    reg = RuleRegistry()

    @rule(
        name="y-rule",
        category="Module Hygiene",
        tier="P2",
        severity="warning",
        default_confidence="high",
        needs_context=True,
        fixable=True,
        registry=reg,
    )
    def _y(ctx):  # pragma: no cover - registration only
        return []

    meta, _ = reg.get("y-rule")
    assert meta.fixable is True
