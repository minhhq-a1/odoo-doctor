"""Frontend must be a scoreable category so future Frontend rules count."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import CATEGORIES, Diagnostic
from odoo_doctor.core.pipeline import mark_score_eligibility


def test_frontend_is_a_known_category():
    assert "Frontend" in CATEGORIES


def test_frontend_high_confidence_finding_is_score_eligible():
    d = Diagnostic(
        module="m",
        file_path="m/static/src/js/x.js",
        line=1,
        column=0,
        rule="frontend-stub",
        category="Frontend",
        severity="warning",
        tier="P2",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="help",
        odoo_version="17.0",
    )
    assert mark_score_eligibility([d]) == [True]
