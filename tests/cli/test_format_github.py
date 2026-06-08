import json
from pathlib import Path
from typer.testing import CliRunner
from odoo_doctor.cli.app import app

runner = CliRunner()


def test_scan_format_github_emits_annotations(fixtures_dir: Path):
    bad_addon = fixtures_dir / "bad_addon"
    result = runner.invoke(app, ["scan", str(bad_addon), "--format", "github"])
    assert result.exit_code == 0
    lines = result.stdout.strip().split("\n")
    # At least some annotations should be emitted
    assert len(lines) > 0
    for line in lines:
        if line.strip():
            assert line.startswith("::")
            assert "file=" in line


def test_scan_json_flag_still_works(fixtures_dir: Path):
    bad_addon = fixtures_dir / "bad_addon"
    result = runner.invoke(app, ["scan", str(bad_addon), "--json"])
    assert result.exit_code == 0
    # Output should be valid JSON
    data = json.loads(result.stdout)
    assert "schema_version" in data
    assert "version" in data
