"""scan --upgrade-report: opt-in report, additive JSON key, nothing else changes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()
CORPUS = Path(__file__).parents[1] / "corpus" / "migration_19"
SAMPLE = Path(__file__).parents[1] / "fixtures" / "sample_addon"
FROZEN_TOP = {
    "version",
    "schema_version",
    "score_schema_version",
    "project_score",
    "top_findings",
    "modules",
}


def _json(*args: str, root: Path = CORPUS, exit_code: int = 0) -> dict:
    result = runner.invoke(app, ["scan", str(root), "--json", *args])
    assert result.exit_code == exit_code, result.output
    return json.loads(result.stdout)


def _upgrade_findings(report: dict) -> int:
    return sum(
        d["category"] == "Upgrade Safety"
        for m in report["modules"].values()
        for d in m["diagnostics"]
    )


def test_json_without_the_flag_has_no_upgrade_report():
    report = _json()
    assert set(report) == FROZEN_TOP


def test_flag_only_adds_the_key():
    plain = _json()
    with_flag = _json("--upgrade-report")
    extra = with_flag.pop("upgrade_report")
    assert with_flag == plain
    assert extra["readiness_schema_version"] == 1
    assert extra["target_version"] == "19.0"


def test_totals_equal_the_upgrade_safety_findings_of_the_scan():
    report = _json("--upgrade-report")
    up = report["upgrade_report"]
    assert up["totals"]["findings"] == _upgrade_findings(report) == 10
    assert (
        sum(m["totals"]["findings"] for m in up["modules"].values())
        == up["totals"]["findings"]
    )
    assert up["totals"]["mechanical"] + up["totals"]["needs_review"] == 10


def test_mixed_removed_field_entries_in_the_corpus():
    up = _json("--upgrade-report")["upgrade_report"]
    groups = {g["group"]: g for g in up["modules"]["mg"]["groups"]}
    fields = groups["Removed core fields"]
    # res.groups.users is a rename; res.groups.category_id is not.
    assert (fields["mechanical"], fields["needs_review"]) == (1, 1)
    assert groups["Kanban legacy templates"]["mechanical"] == 0
    assert groups["View type tree renamed to list"]["needs_review"] == 0


def test_every_module_has_a_score_even_without_findings():
    up = _json("--upgrade-report", root=SAMPLE, exit_code=0)["upgrade_report"]
    assert up["modules"]
    assert all(isinstance(m["score"], float) for m in up["modules"].values())
    up = _json("--upgrade-report", root=CORPUS)["upgrade_report"]
    assert 0 < up["modules"]["mg"]["score"] < 100


def test_target_version_from_the_option():
    up = _json("--upgrade-report", "--odoo-version", "18.0")["upgrade_report"]
    assert up["target_version"] == "18.0"


def test_terminal_prints_the_normal_output_then_the_report():
    plain = runner.invoke(app, ["scan", str(CORPUS)])
    result = runner.invoke(app, ["scan", str(CORPUS), "--upgrade-report"])
    assert result.exit_code == plain.exit_code == 0
    assert result.stdout.startswith(plain.stdout)
    tail = result.stdout[len(plain.stdout) :]
    assert "Upgrade readiness report (target Odoo 19.0)" in tail
    assert "mechanical" in tail and "need review" in tail
    assert "Upgrade readiness" not in plain.stdout


def test_warns_when_the_version_has_no_migration_rules():
    result = runner.invoke(
        app,
        ["scan", str(CORPUS), "--json", "--upgrade-report", "--odoo-version", "17.0"],
    )
    assert result.exit_code == 0
    assert "--odoo-version" in result.stderr
    up = json.loads(result.stdout)["upgrade_report"]
    assert up["totals"]["findings"] == 0
    assert up["modules"]["mg"]["score"] == 100.0
    quiet = runner.invoke(app, ["scan", str(CORPUS), "--json", "--upgrade-report"])
    assert "--odoo-version" not in quiet.stderr


def test_other_formats_ignore_the_flag():
    for fmt in ("sarif", "github"):
        args = ["scan", str(CORPUS), "--format", fmt]
        if fmt == "github":
            args.append("--no-pr-comment")
        base = runner.invoke(app, args)
        flagged = runner.invoke(app, [*args, "--upgrade-report"])
        assert flagged.stdout == base.stdout
        assert flagged.exit_code == base.exit_code


def test_exit_codes_do_not_change():
    for args in (["--fail-on", "error"], ["--min-score", "100"]):
        base = runner.invoke(app, ["scan", str(CORPUS), *args])
        flagged = runner.invoke(app, ["scan", str(CORPUS), *args, "--upgrade-report"])
        assert flagged.exit_code == base.exit_code


def test_module_option_limits_the_report():
    up = _json("--upgrade-report", "--module", "mg")["upgrade_report"]
    assert set(up["modules"]) == {"mg"}
    assert (
        set(_json("--upgrade-report", "--module", "nope")["upgrade_report"]["modules"])
        == set()
    )


def test_baseline_removes_the_known_findings_from_the_report(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    written = runner.invoke(
        app, ["scan", str(CORPUS), "--write-baseline", str(baseline)]
    )
    assert written.exit_code == 0
    report = _json("--upgrade-report", "--baseline", str(baseline))
    assert report["upgrade_report"]["totals"]["findings"] == 0
    # A fully-baselined module is still in the scan: present, readiness 100.
    assert report["upgrade_report"]["modules"]["mg"]["score"] == 100.0
    assert _upgrade_findings(report) == 0


def test_diff_report_matches_the_diff_scan():
    changed = {str((CORPUS / "mg" / "views" / "views.xml").resolve())}
    with patch("odoo_doctor.cli.app._get_changed_files", return_value=changed):
        report = _json("--upgrade-report", "--diff", "main")
    assert report["upgrade_report"]["totals"]["findings"] == _upgrade_findings(report)
    assert set(report["upgrade_report"]["modules"]) == {"mg"}
    assert _upgrade_findings(report) > 0


def test_cache_gives_the_same_report(tmp_path: Path):
    root = tmp_path / "case"
    shutil.copytree(CORPUS, root)
    cold = _json("--upgrade-report", "--cache", root=root)
    warm = _json("--upgrade-report", "--cache", root=root)
    assert (root / ".odoo_doctor_cache").exists()
    assert warm["upgrade_report"] == cold["upgrade_report"]


def test_no_addons_with_the_flag(tmp_path: Path):
    up = _json("--upgrade-report", root=tmp_path)["upgrade_report"]
    assert up["modules"] == {} and up["totals"]["findings"] == 0


def test_flag_is_listed_in_help():
    assert "--upgrade-report" in runner.invoke(app, ["scan", "--help"]).stdout


def _addon(root: Path, version: str) -> Path:
    mod = root / "clean"
    mod.mkdir(parents=True)
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        f"{{'name': 'C', 'version': '{version}.1.0.0', 'depends': ['base'], "
        "'data': [], 'installable': True, 'license': 'LGPL-3'}"
    )
    return root


def _run(root: Path, *args: str):
    result = runner.invoke(
        app, ["scan", str(root), "--json", "--upgrade-report", *args]
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["upgrade_report"], result.stderr


def test_target_is_the_detected_version_for_a_clean_project(tmp_path: Path):
    up, err = _run(_addon(tmp_path, "19.0"))
    assert up["target_version"] == "19.0"
    assert "--odoo-version" not in err
    assert up["modules"]["clean"]["score"] == 100.0


def test_old_detected_version_warns(tmp_path: Path):
    up, err = _run(_addon(tmp_path, "17.0"))
    assert up["target_version"] == "17.0"
    assert "--odoo-version" in err


def test_explicit_option_beats_the_detected_version(tmp_path: Path):
    up, err = _run(_addon(tmp_path, "17.0"), "--odoo-version", "19.0")
    assert up["target_version"] == "19.0"
    assert "--odoo-version" not in err


def test_fully_baselined_project_keeps_target_and_modules(tmp_path: Path):
    root = _addon(tmp_path, "19.0")
    baseline = tmp_path / "b.json"
    runner.invoke(app, ["scan", str(root), "--write-baseline", str(baseline)])
    up, err = _run(root, "--baseline", str(baseline))
    assert up["target_version"] == "19.0"
    assert "clean" in up["modules"]
    assert "--odoo-version" not in err


def _old_manifest_copy(tmp_path: Path) -> Path:
    """The corpus addon with 19.0-style constructs but a 17.0.x manifest version."""
    root = tmp_path / "case"
    shutil.copytree(CORPUS, root)
    (root / "odoo-doctor.toml").unlink()
    manifest = root / "mg" / "__manifest__.py"
    text = manifest.read_text()
    assert "19.0" in text
    manifest.write_text(text.replace("19.0", "17.0"))
    return root


def _plain(root: Path, *args: str) -> dict:
    result = runner.invoke(app, ["scan", str(root), "--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_explicit_target_wins_over_a_17_manifest(tmp_path: Path):
    root = _old_manifest_copy(tmp_path)
    report = _json("--upgrade-report", "--odoo-version", "19.0", root=root)
    up = report["upgrade_report"]
    assert up["totals"]["findings"] == _upgrade_findings(report) > 0
    assert up["modules"]["mg"]["score"] < 100


def test_plain_scan_keeps_the_manifest_gating(tmp_path: Path):
    root = _old_manifest_copy(tmp_path)
    plain = _plain(root, "--odoo-version", "19.0")
    assert _upgrade_findings(plain) == 0


def test_without_a_target_a_17_manifest_warns_once(tmp_path: Path):
    root = _old_manifest_copy(tmp_path)
    result = runner.invoke(app, ["scan", str(root), "--json", "--upgrade-report"])
    assert result.exit_code == 0
    assert result.stderr.count("[WARN]") == 1
    assert "mg (17.0)" in result.stderr and "--odoo-version 19.0" in result.stderr
    assert json.loads(result.stdout)["upgrade_report"]["totals"]["findings"] == 0


def test_cached_report_equals_live_report_with_a_forced_target(tmp_path: Path):
    root = _old_manifest_copy(tmp_path)
    args = ("--upgrade-report", "--odoo-version", "19.0", "--cache")
    cold = _json(*args, root=root)
    warm = _json(*args, root=root)
    assert warm["upgrade_report"] == cold["upgrade_report"]
    assert cold["upgrade_report"]["totals"]["findings"] > 0
    # a plain cached scan must not reuse the forced entry
    assert _upgrade_findings(_plain(root, "--odoo-version", "19.0", "--cache")) == 0
