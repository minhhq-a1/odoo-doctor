# tests/core/test_diagnostics.py
"""Tests for the Diagnostic dataclass and constants."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import (
    CATEGORIES,
    TIER_IMPACT,
    Diagnostic,
)


def test_diagnostic_creation():
    d = Diagnostic(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="raw-sql-string-interpolation",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="SQL injection via string formatting",
        message="cr.execute() uses f-string at line 42",
        help="Use parameterized queries: cr.execute('SELECT ...', (param,))",
        odoo_version="17.0",
        url=None,
    )
    assert d.module == "sale_custom"
    assert d.rule == "raw-sql-string-interpolation"
    assert d.url is None


def test_diagnostic_is_frozen():
    d = Diagnostic(
        module="m",
        file_path="f.py",
        line=1,
        column=0,
        rule="r",
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
    try:
        d.module = "other"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_categories_are_canonical():
    expected = [
        "Security",
        "Correctness",
        "Performance",
        "Data Integrity",
        "Upgrade Safety",
        "Module Hygiene",
        "Maintainability",
        "Frontend",
    ]
    assert CATEGORIES == expected


def test_tier_impact_values():
    assert TIER_IMPACT["P0"] == 25
    assert TIER_IMPACT["P1"] == 10
    assert TIER_IMPACT["P2"] == 4
    assert TIER_IMPACT["P3"] == 1
