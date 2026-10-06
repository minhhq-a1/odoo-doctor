"""`odoo-doctor rules new <rule-name>`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_rules_new_creates_a_plugin_package(tmp_path: Path):
    result = runner.invoke(app, ["rules", "new", "no-print", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    project = tmp_path / "odoo-doctor-rules-no-print"
    assert (project / "pyproject.toml").is_file()
    assert (project / "src" / "odoo_doctor_rules_no_print" / "rules.py").is_file()
    assert "odoo-doctor-rules-no-print" in result.output


def test_rules_new_refuses_to_overwrite(tmp_path: Path):
    runner.invoke(app, ["rules", "new", "no-print", "--out", str(tmp_path)])
    result = runner.invoke(app, ["rules", "new", "no-print", "--out", str(tmp_path)])
    assert result.exit_code == 3
    assert "already exists" in result.output


def test_rules_new_rejects_a_builtin_name(tmp_path: Path):
    result = runner.invoke(app, ["rules", "new", "eval-usage", "--out", str(tmp_path)])
    assert result.exit_code == 3
    assert not (tmp_path / "odoo-doctor-rules-eval-usage").exists()


def test_rules_new_rejects_a_bad_name_and_a_missing_name(tmp_path: Path):
    bad = runner.invoke(app, ["rules", "new", "Not Valid", "--out", str(tmp_path)])
    missing = runner.invoke(app, ["rules", "new", "--out", str(tmp_path)])
    assert bad.exit_code == 3
    assert missing.exit_code == 3
    assert list(tmp_path.iterdir()) == []
