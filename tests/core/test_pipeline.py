# tests/core/test_pipeline.py
"""Tests for the 7-stage diagnostic pipeline."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.pipeline import (
    deduplicate,
    normalize_diagnostics,
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


# --- normalize ---

def test_normalize_converts_paths_to_posix_absolute():
    d = _diag(file_path="models\\sale.py")
    result = normalize_diagnostics([d])
    assert result[0].file_path.endswith("/models/sale.py")
    assert "\\" not in result[0].file_path


def test_run_pipeline_normalizes_before_dedup():
    from pathlib import Path

    file_path = Path("models") / "sale.py"
    file_path.parent.mkdir()
    file_path.touch()
    native = _diag(file_path=str(file_path.resolve()), source="native", message="native")
    adapter = _diag(file_path=str(file_path), source="ruff", message="adapter")
    cfg = OdooDoctorConfig()

    try:
        result_diags, eligible = run_pipeline(
            [native, adapter], cfg, suppressions=set(), active_rules={"r": None},
            detected_version="17.0",
        )

        assert len(result_diags) == 1
        assert len(eligible) == 1
    finally:
        file_path.unlink()
        file_path.parent.rmdir()


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


def test_ignore_by_file_glob_with_normalization_models():
    from pathlib import Path
    base_dir = Path("/tmp/fake_repo")
    file_path = base_dir / "models" / "sale.py"
    d = _diag(file_path=str(file_path))
    
    # Test relative pattern like models/*.py with base_path provided
    cfg = OdooDoctorConfig(ignore_files=["models/*.py"])
    normalized = normalize_diagnostics([d])
    result = apply_ignore_filters(normalized, cfg, base_path=base_dir.resolve())
    assert len(result) == 0


def test_ignore_by_file_glob_with_normalization_migrations():
    from pathlib import Path
    base_dir = Path("/tmp/fake_repo")
    file_path = base_dir / "migrations" / "17.0" / "pre.py"
    d = _diag(file_path=str(file_path))
    
    # Test nested glob pattern like migrations/** with base_path
    cfg = OdooDoctorConfig(ignore_files=["migrations/**"])
    normalized = normalize_diagnostics([d])
    result = apply_ignore_filters(normalized, cfg, base_path=base_dir.resolve())
    assert len(result) == 0


def test_run_pipeline_ignores_relative_patterns(tmp_path):
    # Setup files in tmp_path
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    sale_file = models_dir / "sale.py"
    sale_file.touch()
    
    d = _diag(file_path=str(sale_file))
    cfg = OdooDoctorConfig(ignore_files=["models/*.py"])
    
    result_diags, eligible = run_pipeline(
        [d], cfg, suppressions=set(), active_rules={"r": None},
        detected_version="17.0",
        base_path=tmp_path,
    )
    assert len(result_diags) == 0


def test_run_pipeline_ignores_migrations_glob(tmp_path):
    migrations_dir = tmp_path / "migrations" / "17.0"
    migrations_dir.mkdir(parents=True)
    pre_file = migrations_dir / "pre.py"
    pre_file.touch()
    
    d = _diag(file_path=str(pre_file))
    cfg = OdooDoctorConfig(ignore_files=["migrations/**"])
    
    result_diags, eligible = run_pipeline(
        [d], cfg, suppressions=set(), active_rules={"r": None},
        detected_version="17.0",
        base_path=tmp_path,
    )
    assert len(result_diags) == 0



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


def test_run_pipeline_suppression_matches_after_path_normalization(tmp_path):
    file_path = tmp_path / "models" / "sale.py"
    file_path.parent.mkdir()
    file_path.write_text("")
    d = _diag(file_path=str(file_path), line=10, rule="search-in-loop")

    result_diags, eligible = run_pipeline(
        [d], OdooDoctorConfig(),
        suppressions={(str(file_path), 10, "search-in-loop")},
        active_rules={"search-in-loop": None},
        detected_version="17.0",
    )

    assert result_diags == []
    assert eligible == []


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
