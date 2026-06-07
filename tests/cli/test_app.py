# tests/cli/test_app.py
"""Tests for the CLI app."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_scan_sample_addon(sample_addon: Path):
    result = runner.invoke(app, ["scan", str(sample_addon.parent)])
    assert result.exit_code == 0
    assert "sample_addon" in result.stdout


def test_scan_json_output(sample_addon: Path):
    result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    assert result.exit_code == 0
    import json
    parsed = json.loads(result.stdout)
    assert "modules" in parsed


def test_scan_nonexistent_path():
    result = runner.invoke(app, ["scan", "/nonexistent/path"])
    assert result.exit_code == 0  # no addons found, but doesn't crash


def test_scan_uses_config_addons_paths_when_path_omitted(tmp_path: Path, monkeypatch):
    addons = tmp_path / "addons"
    addons.mkdir()
    mod = addons / "x_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "X", "version": "17.0.1.0.0", "depends": [], "data": [], "license": "LGPL-3"}'
    )
    (tmp_path / "odoo-doctor.toml").write_text('[odoo-doctor]\naddons_paths = ["addons"]\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["scan", "--json"])
    assert result.exit_code == 0
    import json
    parsed = json.loads(result.stdout)
    assert "x_mod" in parsed["modules"]


def test_scan_explicit_path_ignores_config_addons_paths(tmp_path: Path):
    addons = tmp_path / "addons"
    addons.mkdir()
    mod = addons / "x_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "X", "version": "17.0.1.0.0", "depends": [], "data": [], "license": "LGPL-3"}'
    )
    (tmp_path / "odoo-doctor.toml").write_text('[odoo-doctor]\naddons_paths = ["addons"]\n')
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    import json
    parsed = json.loads(result.stdout)
    assert parsed["modules"] == {}


def test_rules_list():
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0
    assert "missing-access-csv" in result.stdout


def test_init_creates_config(tmp_path: Path):
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "odoo-doctor.toml").exists()


def test_install(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0
    assert "Installed skill: odoo-doctor" in result.stdout
    assert "Installed skill: odoo-doctor-explain" in result.stdout
    skills_dir = tmp_path / ".odoo-doctor" / "skills"
    assert (skills_dir / "odoo-doctor" / "SKILL.md").exists()
    assert (skills_dir / "odoo-doctor-explain" / "SKILL.md").exists()


def test_scan_warns_on_adapter_crash(tmp_path: Path):
    """Adapter crash should produce a stderr warning, not silent swallow."""
    mod = tmp_path / "x_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "X", "version": "17.0.1.0.0", "depends": [], "data": [], "license": "LGPL-3"}'
    )
    (tmp_path / "odoo-doctor.toml").write_text("[adapters]\nruff = false\npylint_odoo = false\n")

    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0

def test_fail_on_warning_fails_for_errors(bad_addon: Path):
    """--fail-on warning means warning or anything more severe."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--fail-on", "warning"])
    assert result.exit_code == 1
