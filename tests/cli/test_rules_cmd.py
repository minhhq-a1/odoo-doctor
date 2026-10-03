"""`odoo-doctor rules` subcommands: explain, disable/enable, docs."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app
from odoo_doctor.core.config import load_config

runner = CliRunner()


def test_explain_renders_catalog_content_and_docs_link():
    result = runner.invoke(app, ["rules", "explain", "eval-usage"])
    assert result.exit_code == 0
    assert "Rule: eval-usage" in result.stdout
    assert "Detects:" in result.stdout
    assert "Good:" in result.stdout
    assert "docs/rules.md#eval-usage" in result.stdout


def test_disable_creates_config_and_scan_config_sees_it(tmp_path: Path):
    result = runner.invoke(
        app, ["rules", "disable", "orphan-view", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert load_config(tmp_path).ignore_rules == ["orphan-view"]


def test_disable_is_idempotent_and_enable_reverts(tmp_path: Path):
    args = ["--path", str(tmp_path)]
    runner.invoke(app, ["rules", "disable", "orphan-view", *args])
    again = runner.invoke(app, ["rules", "disable", "orphan-view", *args])
    assert "already disabled" in again.stdout
    runner.invoke(app, ["rules", "enable", "orphan-view", *args])
    assert load_config(tmp_path).ignore_rules == []


def test_disable_unknown_rule_exits_3(tmp_path: Path):
    result = runner.invoke(app, ["rules", "disable", "nope", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert not (tmp_path / "odoo-doctor.toml").exists()


def test_list_marks_disabled_rules(tmp_path: Path):
    runner.invoke(app, ["rules", "disable", "orphan-view", "--path", str(tmp_path)])
    result = runner.invoke(app, ["rules", "list", "--path", str(tmp_path)])
    line = next(ln for ln in result.stdout.splitlines() if "orphan-view" in ln)
    assert "(disabled)" in line


def test_docs_to_stdout_and_file_and_check(tmp_path: Path):
    out = tmp_path / "rules.md"
    assert runner.invoke(app, ["rules", "docs", "--out", str(out)]).exit_code == 0
    assert "### eval-usage" in out.read_text(encoding="utf-8")
    ok = runner.invoke(app, ["rules", "docs", "--out", str(out), "--check"])
    assert ok.exit_code == 0
    out.write_text("stale", encoding="utf-8")
    stale = runner.invoke(app, ["rules", "docs", "--out", str(out), "--check"])
    assert stale.exit_code == 1


def test_docs_html_format():
    result = runner.invoke(app, ["rules", "docs", "--format", "html"])
    assert result.exit_code == 0
    assert result.stdout.startswith("<!doctype html>")


def test_docs_rejects_bad_format():
    result = runner.invoke(app, ["rules", "docs", "--format", "pdf"])
    assert result.exit_code == 3


def test_unknown_action_exits_3():
    assert runner.invoke(app, ["rules", "frobnicate"]).exit_code == 3
