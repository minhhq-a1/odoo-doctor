"""Score history: records, legacy normalization, trend and regression detection."""

from __future__ import annotations

import json
from pathlib import Path

from odoo_doctor.core.history import (
    HISTORY_SCHEMA_VERSION,
    append_record,
    build_record,
    detect_regressions,
    load_history,
    normalize_record,
    normalize_report,
    to_utc_iso,
)
from odoo_doctor.core.scoring import SCORE_SCHEMA_VERSION, ScoreResult, score_label


def _score(overall: float) -> ScoreResult:
    return ScoreResult(
        overall=overall,
        label=score_label(overall),
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=0,
    )


def _rec(ts, overall, *, schema=SCORE_SCHEMA_VERSION, branch="main", mods=None):
    return {
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "score_schema_version": schema,
        "timestamp": ts,
        "branch": branch,
        "commit": None,
        "project": {"overall": overall, "label": score_label(overall)},
        "modules": {k: {"overall": v} for k, v in (mods or {}).items()},
    }


# A real v0.3.0 report shape: no score_schema_version.
LEGACY_REPORT = {
    "version": "0.3.0",
    "schema_version": "1.0",
    "project_score": {"overall": 80.0, "label": "Good", "module_count": 2},
    "top_findings": [],
    "modules": {
        "a": {"score": {"overall": 90.0, "label": "Excellent"}, "diagnostics": []},
        "b": {"score": {"overall": 70.0, "label": "Needs work"}, "diagnostics": []},
    },
}


def test_build_record_shape():
    rec = build_record(
        {"a": _score(90.0), "b": _score(70.0)},
        tool_version="9.9.9",
        commit="abc",
        branch="main",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    assert rec["history_schema_version"] == HISTORY_SCHEMA_VERSION
    assert rec["score_schema_version"] == SCORE_SCHEMA_VERSION
    assert rec["project"]["overall"] == 80.0
    assert rec["modules"]["a"] == {"overall": 90.0, "label": "Excellent"}
    json.dumps(rec)  # serializable


def test_legacy_report_is_normalized_as_schema_1():
    rec = normalize_report(LEGACY_REPORT, timestamp="2026-01-01T00:00:00+00:00")
    assert rec["score_schema_version"] == 1
    assert rec["score_schema_inferred"] is True
    assert rec["tool_version"] == "0.3.0"
    assert rec["project"]["overall"] == 80.0
    assert set(rec["modules"]) == {"a", "b"}
    assert rec["normalized_from"] == "report"


def test_legacy_report_without_project_score_uses_module_mean():
    report = {k: v for k, v in LEGACY_REPORT.items() if k != "project_score"}
    assert normalize_report(report)["project"]["overall"] == 80.0


def test_current_report_keeps_declared_schema():
    report = dict(LEGACY_REPORT, score_schema_version=2)
    rec = normalize_report(report)
    assert rec["score_schema_version"] == 2
    assert "score_schema_inferred" not in rec


def test_unusable_reports_return_none():
    assert normalize_report({}) is None
    assert normalize_report({"modules": {}}) is None
    assert normalize_report({"modules": {"a": {"score": {"overall": "x"}}}}) is None
    assert normalize_record(["not", "a", "dict"]) is None
    assert normalize_record({"history_schema_version": 1}) is None


def test_normalize_record_accepts_raw_report_lines():
    assert normalize_record(LEGACY_REPORT)["score_schema_version"] == 1


def test_append_and_load_sorted_and_tolerant(tmp_path: Path):
    path = tmp_path / "sub" / "h.jsonl"
    append_record(path, _rec("2026-03-01T00:00:00+00:00", 70))
    append_record(path, _rec("2026-01-01T00:00:00+00:00", 90))
    with path.open("a") as fh:
        fh.write("{not json\n\n[]\n")
    records, skipped = load_history(path)
    assert [r["project"]["overall"] for r in records] == [90, 70]
    assert skipped == 2


def test_load_missing_file_is_empty(tmp_path: Path):
    assert load_history(tmp_path / "nope.jsonl") == ([], 0)


def test_to_utc_iso_normalizes_offsets():
    assert to_utc_iso("2026-01-01T07:00:00+07:00") == "2026-01-01T00:00:00+00:00"
    assert to_utc_iso("2026-01-01T00:00:00Z") == "2026-01-01T00:00:00+00:00"
    assert to_utc_iso("2026-01-01T00:00:00") == "2026-01-01T00:00:00+00:00"


def test_regression_project_and_module():
    records = [
        _rec("2026-01-01T00:00:00+00:00", 90, mods={"a": 90, "b": 90}),
        _rec("2026-01-02T00:00:00+00:00", 80, mods={"a": 90, "b": 70}),
    ]
    found = {r["scope"]: r for r in detect_regressions(records)}
    assert found["project"]["drop"] == 10.0
    assert found["b"]["drop"] == 20.0
    assert "a" not in found


def test_regression_threshold_is_strict():
    records = [
        _rec("2026-01-01T00:00:00+00:00", 90),
        _rec("2026-01-02T00:00:00+00:00", 88),
    ]
    assert detect_regressions(records, max_drop=2.0) == []
    assert len(detect_regressions(records, max_drop=1.9)) == 1


def test_improvement_and_single_record_are_not_regressions():
    up = [_rec("2026-01-01T00:00:00+00:00", 70), _rec("2026-01-02T00:00:00+00:00", 90)]
    assert detect_regressions(up) == []
    assert detect_regressions(up[:1]) == []


def test_schema_change_is_never_flagged_as_regression():
    records = [
        _rec("2026-01-01T00:00:00+00:00", 95, schema=1),
        _rec("2026-01-02T00:00:00+00:00", 60, schema=2),
    ]
    assert detect_regressions(records) == []


def test_comparison_stays_within_the_same_branch():
    records = [
        _rec("2026-01-01T00:00:00+00:00", 90, branch="main"),
        _rec("2026-01-02T00:00:00+00:00", 50, branch="feature"),
        _rec("2026-01-03T00:00:00+00:00", 85, branch="main"),
    ]
    found = detect_regressions(records)
    assert [r["drop"] for r in found] == [5.0]


def test_malformed_module_entries_are_ignored_not_fatal():
    prev = _rec("2026-01-01T00:00:00+00:00", 90)
    prev["modules"] = {"a": {"overall": 90}, "b": "garbage", "c": {}}
    last = _rec("2026-01-02T00:00:00+00:00", 80)
    last["modules"] = {"a": {"overall": 70}, "b": {"overall": 1}, "c": None}
    found = {r["scope"] for r in detect_regressions([prev, last])}
    assert found == {"project", "a"}
