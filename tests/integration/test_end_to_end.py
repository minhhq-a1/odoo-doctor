# tests/integration/test_end_to_end.py
"""End-to-end integration test — scan bad_addon and verify results."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_end_to_end_bad_addon(bad_addon: Path):
    """Scan bad_addon and verify it catches the expected issues."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--json"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "bad_addon" in parsed["modules"]

    mod = parsed["modules"]["bad_addon"]
    rules_found = {d["rule"] for d in mod["diagnostics"]}

    # Must catch these (success criteria from spec):
    assert "missing-access-csv" in rules_found, "Should catch missing access rules"
    assert "raw-sql-string-interpolation" in rules_found, "Should catch unsafe SQL"
    assert "duplicate-xml-id" in rules_found, "Should catch duplicate XML IDs"

    # Score should be below 100 (issues found)
    assert mod["score"]["overall"] < 100


def test_end_to_end_clean_addon(sample_addon: Path):
    """Scan sample_addon — should have few or no high-confidence findings."""
    result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "sample_addon" in parsed["modules"]

    mod = parsed["modules"]["sample_addon"]
    high_confidence = [d for d in mod["diagnostics"] if d["confidence"] == "high"]

    # Clean addon should have minimal high-confidence findings
    # (may have some from adapters if installed, but native rules should be clean)
    native_high = [d for d in high_confidence if d["source"] == "native"]
    assert len(native_high) == 0, (
        f"Clean addon should have no native high-confidence findings: {native_high}"
    )


def test_end_to_end_terminal_output(bad_addon: Path):
    """Verify terminal output renders without crashing."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent)])
    assert result.exit_code == 0
    assert "bad_addon" in result.stdout
    assert "Score:" in result.stdout or "score" in result.stdout.lower()


def test_end_to_end_fail_on(bad_addon: Path):
    """--fail-on error should exit non-zero when errors exist."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--fail-on", "error"])
    assert result.exit_code != 0
