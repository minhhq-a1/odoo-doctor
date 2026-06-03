# tests/core/test_pipeline.py
"""Tests for the 7-stage diagnostic pipeline."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.pipeline import (
    deduplicate,
    apply_severity_overrides,
    apply_ignore_filters,
    apply_inline_suppressions,
    apply_version_gates,
    mark_score_eligibility,
    run_pipeline,
)


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


# --- deduplicate ---

def test_dedup_same_file_line_category_keeps_higher_confidence():
    native_low = _diag(source="native", confidence="low", message="short")
    adapter_high = _diag(source="ruff", confidence="high", message="detailed msg")
    result = deduplicate([native_low, adapter_high])
    assert len(result) == 1
    assert result[0].confidence == "high"


def test_dedup_different_categories_kept():
    sec = _diag(category="Security", rule="r1")
    cor = _diag(category="Correctness", rule="r2")
    result = deduplicate([sec, cor])
    assert len(result) == 2


def test_dedup_same_confidence_prefers_native():
    native = _diag(source="native", message="native msg")
    adapter = _diag(source="ruff", message="adapter msg")
    result = deduplicate([native, adapter])
    assert len(result) == 1
    assert result[0].source == "native"


# --- severity overrides ---

def test_severity_override_changes_severity():
    d = _diag(rule="search-in-loop", severity="error")
    cfg = OdooDoctorConfig(severity_overrides={"search-in-loop": "warning"})
    result = apply_severity_overrides([d], cfg)
    assert result[0].severity == "warning"


def test_severity_override_off_removes():
    d = _diag(rule="search-in-loop")
    cfg = OdooDoctorConfig(severity_overrides={"search-in-loop": "off"})
    result = apply_severity_overrides([d], cfg)
    assert len(result) == 0


# --- ignore filters ---

def test_ignore_by_rule():
    d = _diag(rule="deprecated-api")
    cfg = OdooDoctorConfig(ignore_rules=["deprecated-api"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


def test_ignore_by_module():
    d = _diag(module="legacy")
    cfg = OdooDoctorConfig(ignore_modules=["legacy"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


def test_ignore_by_file_glob():
    d = _diag(file_path="migrations/17.0/pre.py")
    cfg = OdooDoctorConfig(ignore_files=["**/migrations/**"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


# --- inline suppressions ---

def test_inline_suppression_removes_matching():
    d = _diag(file_path="models/sale.py", line=10, rule="search-in-loop")
    suppressions = {("models/sale.py", 10, "search-in-loop")}
    result = apply_inline_suppressions([d], suppressions)
    assert len(result) == 0


def test_inline_suppression_keeps_non_matching():
    d = _diag(file_path="models/sale.py", line=10, rule="search-in-loop")
    suppressions = {("models/sale.py", 10, "other-rule")}
    result = apply_inline_suppressions([d], suppressions)
    assert len(result) == 1


# --- version gates ---

def test_version_gate_removes_inapplicable():
    d = _diag(rule="owl-rule", odoo_version="14.0")
    active_rules = {"search-in-loop": "14.0", "owl-rule": "16.0"}
    result = apply_version_gates([d], active_rules, detected_version="14.0")
    assert len(result) == 0


def test_version_gate_keeps_applicable():
    d = _diag(rule="search-in-loop", odoo_version="17.0")
    active_rules = {"search-in-loop": "14.0"}
    result = apply_version_gates([d], active_rules, detected_version="17.0")
    assert len(result) == 1


def test_version_gate_keeps_when_no_min():
    d = _diag(rule="raw-sql")
    active_rules = {"raw-sql": None}
    result = apply_version_gates([d], active_rules, detected_version="17.0")
    assert len(result) == 1


# --- score eligibility ---

def test_score_eligible_high_confidence():
    d = _diag(confidence="high", category="Security")
    result = mark_score_eligibility([d])
    assert result[0] is True


def test_score_ineligible_low_confidence():
    d = _diag(confidence="low", category="Security")
    result = mark_score_eligibility([d])
    assert result[0] is False


def test_score_ineligible_uncategorized():
    d = _diag(confidence="high", category="Uncategorized")
    result = mark_score_eligibility([d])
    assert result[0] is False


# --- full pipeline ---

def test_run_pipeline_smoke():
    diags = [_diag(rule="r1"), _diag(rule="r2", confidence="low")]
    cfg = OdooDoctorConfig()
    active_rules = {"r1": None, "r2": None}
    result_diags, eligible = run_pipeline(
        diags, cfg, suppressions=set(), active_rules=active_rules,
        detected_version="17.0",
    )
    assert len(result_diags) == 2
    assert eligible[0] is True   # r1: high confidence
    assert eligible[1] is False  # r2: low confidence
