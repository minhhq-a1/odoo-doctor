# tests/cli/test_min_score_and_diff.py
"""Tests for --min-score enforcement and --diff path matching."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


# ─── Task 1: --min-score ────────────────────────────────────────────────────

def test_min_score_passes_when_above_threshold(sample_addon: Path):
    """Clean addon scores high → exit 0 when min-score is low."""
    result = runner.invoke(app, ["scan", str(sample_addon), "--min-score", "0"])
    assert result.exit_code == 0


def test_min_score_fails_when_below_threshold(bad_addon: Path):
    """bad_addon will score below 100 → exit 2 when min-score=100."""
    result = runner.invoke(app, ["scan", str(bad_addon), "--min-score", "100"])
    assert result.exit_code == 2


def test_min_score_from_config(tmp_path: Path):
    """min_score from odoo-doctor.toml is enforced when --min-score not passed."""
    mod = tmp_path / "bad_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Bad", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "models").mkdir()
    (mod / "models" / "m.py").write_text(
        'from odoo import models\nclass M(models.Model):\n    _name = "bad.model"\n'
    )
    # Config sets min_score = 100 — should fail because missing-access-csv fires
    (tmp_path / "odoo-doctor.toml").write_text("[odoo-doctor]\nmin_score = 100\n")
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 2


def test_min_score_cli_overrides_config(tmp_path: Path):
    """CLI --min-score=0 overrides config min_score=100 → should pass."""
    mod = tmp_path / "bad_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Bad", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (tmp_path / "odoo-doctor.toml").write_text("[odoo-doctor]\nmin_score = 100\n")
    result = runner.invoke(app, ["scan", str(tmp_path), "--min-score", "0"])
    assert result.exit_code == 0


def test_min_score_json_output_still_exits_2(bad_addon: Path):
    """--json + --min-score still exits 2 (no terminal output for fail message)."""
    result = runner.invoke(app, ["scan", str(bad_addon), "--min-score", "100", "--json"])
    assert result.exit_code == 2
    # JSON should still be valid on stdout
    parsed = json.loads(result.stdout)
    assert "modules" in parsed


# ─── Task 3: --diff path matching ───────────────────────────────────────────

def test_diff_filters_by_absolute_path(tmp_path: Path, bad_addon: Path):
    """--diff only returns diags for the changed files (absolute path match)."""
    changed_file = bad_addon / "models" / "bad_model.py"

    with patch("odoo_doctor.cli.app._get_changed_files", return_value={str(changed_file)}):
        result = runner.invoke(app, [
            "scan", str(bad_addon.parent),
            "--diff", "main",  # value doesn't matter, _get_changed_files is mocked
            "--json",
        ])

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    # File-based diags come from the changed file; context diags for the changed module are retained.
    bad_diags = parsed["modules"].get("bad_addon", {}).get("diagnostics", [])
    assert bad_diags
    for d in bad_diags:
        assert "bad_model.py" in d["file_path"] or d["rule"] != "raw-sql-string-interpolation"


def test_diff_filters_when_scan_path_is_not_repo_root(bad_addon: Path):
    """Absolute changed paths still match when scanning a subdirectory."""
    changed_file = bad_addon / "models" / "bad_model.py"

    with patch("odoo_doctor.cli.app._get_changed_files", return_value={str(changed_file)}):
        result = runner.invoke(app, [
            "scan", str(bad_addon.parent),
            "--diff", "main",
            "--json",
        ])

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    bad_diags = parsed["modules"].get("bad_addon", {}).get("diagnostics", [])
    assert bad_diags
    assert any(Path(d["file_path"]).resolve() == changed_file.resolve() for d in bad_diags)
    assert all(
        Path(d["file_path"]).resolve() == changed_file.resolve()
        or d["rule"] != "raw-sql-string-interpolation"
        for d in bad_diags
    )


def test_diff_empty_changed_files_returns_no_diags(bad_addon: Path):
    """--diff with no changed files → no diagnostics."""
    with patch("odoo_doctor.cli.app._get_changed_files", return_value=set()):
        result = runner.invoke(app, [
            "scan", str(bad_addon.parent),
            "--diff", "main",
            "--json",
        ])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    all_diags = [
        d
        for mod in parsed["modules"].values()
        for d in mod["diagnostics"]
    ]
    assert all_diags == []

def test_diff_keeps_context_diagnostics_for_changed_module(tmp_path: Path):
    """Changing a model file should keep context findings such as missing ACLs."""
    mod = tmp_path / "acl_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "ACL Mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    models_dir = mod / "models"
    models_dir.mkdir()
    model_file = models_dir / "m.py"
    model_file.write_text(
        'from odoo import models\nclass M(models.Model):\n    _name = "acl.mod"\n'
    )

    with patch("odoo_doctor.cli.app._get_changed_files", return_value={str(model_file)}):
        result = runner.invoke(app, [
            "scan", str(tmp_path),
            "--diff", "main",
            "--json",
        ])

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    diags = parsed["modules"]["acl_mod"]["diagnostics"]
    assert any(d["rule"] == "missing-access-csv" for d in diags)


# ─── Part C / C1: --diff failure semantics ──────────────────────────────────

import subprocess
import odoo_doctor.cli.app as appmod


def test_get_changed_files_returns_none_on_git_failure(tmp_path: Path, monkeypatch):
    """git rev-parse failing (not a repo / unknown ref) → None, not empty set."""
    monkeypatch.setattr(
        appmod.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 128, stdout="", stderr="fatal"),
    )
    assert appmod._get_changed_files(tmp_path, "nope") is None


def test_get_changed_files_empty_diff_returns_empty_set(tmp_path: Path, monkeypatch):
    """git succeeds but nothing changed → empty set (a valid 'scan nothing' run)."""
    calls = iter([
        subprocess.CompletedProcess([], 0, stdout=str(tmp_path), stderr=""),  # rev-parse
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),             # diff (empty)
    ])
    monkeypatch.setattr(appmod.subprocess, "run", lambda *a, **k: next(calls))
    assert appmod._get_changed_files(tmp_path, "main") == set()


def test_diff_git_failure_exits_3(bad_addon: Path):
    """A --diff git failure must error out (exit 3), never a clean exit 0."""
    with patch("odoo_doctor.cli.app._get_changed_files", return_value=None):
        result = runner.invoke(app, [
            "scan", str(bad_addon.parent), "--diff", "does-not-exist", "--json",
        ])
    assert result.exit_code == 3

