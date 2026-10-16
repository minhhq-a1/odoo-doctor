"""scripts/measure.py: grouping, comparing, and one real run on a tiny fixture."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "measure", ROOT / "scripts" / "measure.py"
)
measure = importlib.util.module_from_spec(_SPEC)
sys.modules["measure"] = measure
_SPEC.loader.exec_module(measure)

SAMPLE = ROOT / "tests" / "fixtures" / "sample_addon"


def diag(rule: str, confidence: str, source: str = "native") -> dict:
    return {"rule": rule, "confidence": confidence, "source": source}


def payload(*diags: dict, score: float = 90.0) -> dict:
    return {
        "project_score": {"overall": score},
        "modules": {"m": {"score": {"overall": score}, "diagnostics": list(diags)}},
    }


def row(high: int = 0, medium: int = 0, low: int = 0) -> dict:
    return {"high": high, "medium": medium, "low": low}


def target(rules: dict, **over) -> dict:
    base = {
        "path": "/x",
        "commit": "abc",
        "odoo_version": "19.0",
        "config_sha256": "",
        "modules": 1,
        "findings": 0,
        "project_score": 90.0,
        "module_scores": {},
        "seconds": 1.0,
        "rules": rules,
    }
    base.update(over)
    return base


def snap(**targets: dict) -> dict:
    return {"tool_version": "0.9.3", "targets": targets}


# --- parse_target ------------------------------------------------------------


def test_parse_target_plain_and_with_version():
    assert measure.parse_target("skw=/a/b") == ("skw", "/a/b", None)
    assert measure.parse_target("core=/a/addons@19.0") == ("core", "/a/addons", "19.0")


def test_parse_target_keeps_an_at_sign_that_is_not_a_version():
    assert measure.parse_target("x=/home/me@work/addons") == (
        "x",
        "/home/me@work/addons",
        None,
    )


@pytest.mark.parametrize("bad", ["nolabel", "=path", "label="])
def test_parse_target_rejects_malformed(bad: str):
    with pytest.raises(ValueError):
        measure.parse_target(bad)


# --- summarize ---------------------------------------------------------------


def test_summarize_groups_by_source_rule_and_confidence():
    s = measure.summarize(
        payload(
            diag("a", "high"),
            diag("a", "high"),
            diag("a", "low"),
            diag("E501", "medium", source="ruff"),
            score=88.5,
        )
    )
    assert s["modules"] == 1 and s["findings"] == 4 and s["project_score"] == 88.5
    assert s["module_scores"] == {"m": 88.5}
    assert s["rules"] == {
        "native/a": row(high=2, low=1),
        "ruff/E501": row(medium=1),
    }


# --- compare -----------------------------------------------------------------


def test_compare_allows_audit_rules_to_change():
    before = snap(c=target({"native/manifest-data-order-risk": row(high=52)}))
    after = snap(c=target({"native/manifest-data-order-risk": row(high=1, medium=51)}))
    lines, regressions, incomparable, _ = measure.compare(before, after)
    assert regressions == [] and incomparable == []
    assert lines == ["c native/manifest-data-order-risk: high 52->1, medium 0->51"]


def test_compare_flags_a_total_increase_of_a_non_audit_rule():
    before = snap(c=target({"native/eval-usage": row(high=2)}))
    after = snap(c=target({"native/eval-usage": row(high=2, low=3)}))
    _, regressions, _, _ = measure.compare(before, after)
    assert regressions == ["c native/eval-usage: total 2 -> 5"]


def test_compare_flags_medium_turning_high_even_when_the_total_is_equal():
    before = snap(c=target({"native/eval-usage": row(medium=2)}))
    after = snap(c=target({"native/eval-usage": row(high=1, medium=1)}))
    _, regressions, _, _ = measure.compare(before, after)
    assert regressions == ["c native/eval-usage: high 0 -> 1"]


def test_compare_keeps_native_and_adapter_counts_apart():
    before = snap(c=target({"native/E501": row(high=5), "ruff/E501": row(high=1)}))
    after = snap(c=target({"native/E501": row(high=5), "ruff/E501": row(high=4)}))
    _, regressions, _, _ = measure.compare(before, after)
    assert regressions == [
        "c ruff/E501: total 1 -> 4",
        "c ruff/E501: high 1 -> 4",
    ]


def test_compare_reports_incomparable_inputs():
    before = snap(c=target({}, commit="aaa"), gone=target({}))
    after = snap(c=target({}, commit="bbb", config_sha256="zz"), new=target({}))
    after["tool_version"] = "0.10.0"
    _, _, incomparable, _ = measure.compare(before, after)
    assert "tool_version '0.9.3' -> '0.10.0'" in incomparable
    assert "c: commit 'aaa' -> 'bbb'" in incomparable
    assert "c: config_sha256 '' -> 'zz'" in incomparable
    assert "gone: only in before" in incomparable
    assert "new: only in after" in incomparable


def test_compare_lists_module_score_changes_for_every_target():
    before = snap(c=target({}, module_scores={"a": 90.0, "b": 80.0, "gone": 70.0}))
    after = snap(c=target({}, module_scores={"a": 90.0, "b": 75.5, "new": 60.0}))
    _, _, _, scores = measure.compare(before, after)
    assert scores == [
        "c b: 80.0 -> 75.5",
        "c gone: 70.0 -> absent",
        "c new: absent -> 60.0",
    ]


def test_compare_of_identical_snapshots_is_silent():
    s = snap(c=target({"native/eval-usage": row(high=2)}))
    assert measure.compare(s, s) == ([], [], [], [])


# --- config / git helpers ----------------------------------------------------


def test_config_sha256_hashes_the_toml_chain_and_is_empty_without_one(tmp_path: Path):
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    assert measure.config_sha256(str(inner)) == ""
    (tmp_path / "odoo-doctor.toml").write_text("[odoo-doctor]\n")
    first = measure.config_sha256(str(inner))
    assert len(first) == 64
    (tmp_path / "a" / "odoo-doctor.toml").write_text("[adapters]\n")
    assert measure.config_sha256(str(inner)) != first


def test_git_commit_is_none_outside_a_repo(tmp_path: Path):
    assert measure.git_commit(str(tmp_path)) is None


# --- one real run ------------------------------------------------------------


def test_main_snapshot_then_compare_with_itself(tmp_path: Path, capsys):
    out = tmp_path / "snap.json"
    spec = f"sample={SAMPLE}@17.0"
    assert measure.main([spec, "--snapshot", str(out)]) == 0
    data = json.loads(out.read_text())
    t = data["targets"]["sample"]
    assert data["tool_version"] and t["modules"] >= 1 and t["findings"] >= 0
    assert set(t) >= {"path", "commit", "odoo_version", "config_sha256", "rules"}
    assert t["odoo_version"] == "17.0"
    capsys.readouterr()
    assert measure.main([spec, "--compare", str(out)]) == 0
    assert "REGRESSION" not in capsys.readouterr().out


def test_main_needs_a_target(monkeypatch, capsys):
    monkeypatch.delenv(measure.TARGETS_ENV, raising=False)
    with pytest.raises(SystemExit):
        measure.main([])
