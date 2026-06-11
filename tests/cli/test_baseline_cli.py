"""Baseline CLI: write a baseline, then new scans pass under it."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def _addon(root: Path) -> Path:
    mod = root / "my_addon"
    mod.mkdir()
    (mod / "__init__.py").touch()
    # Missing license -> at least one finding to baseline.
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], "
        "'data': [], 'installable': True}"
    )
    return mod


def test_write_then_apply_baseline_suppresses_existing(tmp_path: Path):
    _addon(tmp_path)
    bfile = tmp_path / "baseline.json"

    # Write baseline.
    w = runner.invoke(
        app, ["scan", str(tmp_path), "--write-baseline", str(bfile)]
    )
    assert w.exit_code == 0
    assert bfile.exists()

    # Apply baseline with --fail-on warning: existing findings are suppressed,
    # so exit code should be 0.
    a = runner.invoke(
        app,
        ["scan", str(tmp_path), "--baseline", str(bfile), "--fail-on", "warning"],
    )
    assert a.exit_code == 0
