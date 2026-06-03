# tests/rules/test_registry.py
"""Tests for the rule registry and @rule decorator."""

from __future__ import annotations

from odoo_doctor.rules.registry import RuleMeta, RuleRegistry, rule


def test_register_rule():
    reg = RuleRegistry()

    @rule(
        name="test-rule",
        category="Security",
        tier="P1",
        severity="error",
        default_confidence="high",
        needs_context=True,
        registry=reg,
    )
    def check_test(ctx):
        return []

    assert len(reg) == 1
    assert "test-rule" in reg


def test_get_rules_by_context():
    reg = RuleRegistry()

    @rule(
        name="ctx-rule", category="Security", tier="P1", severity="error",
        default_confidence="high", needs_context=True, registry=reg,
    )
    def ctx_func(ctx): return []

    @rule(
        name="file-rule", category="Performance", tier="P2", severity="warning",
        default_confidence="medium", needs_context=False, registry=reg,
    )
    def file_func(f, m, v): return []

    ctx_rules = reg.get_rules(needs_context=True)
    file_rules = reg.get_rules(needs_context=False)
    assert len(ctx_rules) == 1
    assert ctx_rules[0][0].name == "ctx-rule"
    assert len(file_rules) == 1
    assert file_rules[0][0].name == "file-rule"


def test_active_rules_map():
    reg = RuleRegistry()

    @rule(
        name="ver-rule", category="Security", tier="P1", severity="error",
        default_confidence="high", needs_context=True, min_version="16.0", registry=reg,
    )
    def vr(ctx): return []

    rules_map = reg.active_rules_map()
    assert rules_map["ver-rule"] == "16.0"
