# tests/integration/test_e2e.py
"""End-to-end integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_e2e_scan_sample_addon_json(sample_addon: Path):
    """Full scan of sample_addon produces valid JSON with a score."""
    result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "modules" in parsed
    assert "sample_addon" in parsed["modules"]
    module = parsed["modules"]["sample_addon"]
    assert 0 <= module["score"]["overall"] <= 100
    assert module["score"]["label"] in ("Excellent", "Good", "Needs work", "Critical")


def test_e2e_scan_bad_addon_finds_sql_injection(bad_addon: Path):
    """Full scan of bad_addon finds SQL injection."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    all_diags = parsed["modules"]["bad_addon"]["diagnostics"]
    sql_diags = [d for d in all_diags if d["rule"] == "raw-sql-string-interpolation"]
    assert len(sql_diags) >= 1
    assert sql_diags[0]["tier"] == "P0"
    assert sql_diags[0]["category"] == "Security"


def test_e2e_scan_bad_addon_finds_missing_access(bad_addon: Path):
    """Full scan of bad_addon finds missing access CSV."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    all_diags = parsed["modules"]["bad_addon"]["diagnostics"]
    access_diags = [d for d in all_diags if d["rule"] == "missing-access-csv"]
    assert len(access_diags) >= 1


def test_e2e_scan_bad_addon_score_lower_than_sample(
    sample_addon: Path, bad_addon: Path
):
    """bad_addon should score lower than sample_addon."""
    sample_result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    bad_result = runner.invoke(app, ["scan", str(bad_addon.parent), "--json"])
    assert sample_result.exit_code == 0
    assert bad_result.exit_code == 0

    sample_score = json.loads(sample_result.stdout)["modules"]["sample_addon"]["score"][
        "overall"
    ]
    bad_score = json.loads(bad_result.stdout)["modules"]["bad_addon"]["score"][
        "overall"
    ]
    assert bad_score < sample_score


def test_e2e_fail_on_error_exits_1(bad_addon: Path):
    """--fail-on error should exit with code 1 when errors exist."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--fail-on", "error"])
    assert result.exit_code == 1


def test_e2e_init_then_scan(tmp_path: Path):
    """init creates config, then scan uses it."""
    mod = tmp_path / "clean_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Clean", "version": "17.0.1.0.0", "depends": ["base"], "data": [], "license": "LGPL-3"}'
    )
    init_result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert init_result.exit_code == 0

    scan_result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert scan_result.exit_code == 0
    parsed = json.loads(scan_result.stdout)
    assert "clean_mod" in parsed["modules"]
