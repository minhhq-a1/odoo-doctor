# tests/cli/test_adapter_gating.py
"""Tests for adapter execution gating in the CLI based on availability and explicit config."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_adapter_gating_scenarios(tmp_path: Path, monkeypatch):
    # Setup a dummy addon
    mod = tmp_path / "dummy_addon"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Dummy Addon", "version": "17.0.1.0.0", "depends": [], "data": [], "license": "LGPL-3"}'
    )

    # 1. Default config + missing executable => no adapter warnings
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    # Run with default config (no odoo-doctor.toml)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    all_diags = []
    for m in data.get("modules", {}).values():
        all_diags.extend(m.get("diagnostics", []))
    assert not any(d["rule"].startswith("adapter-") for d in all_diags)

    # 2. [adapters] ruff = true + missing executable => adapter-ruff-warning
    (tmp_path / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = true\npylint_odoo = false\n"
    )
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    all_diags = []
    for m in data.get("modules", {}).values():
        all_diags.extend(m.get("diagnostics", []))
    # Should have adapter-ruff-warning because ruff was explicitly set to true but is missing
    assert any(d["rule"] == "adapter-ruff-warning" for d in all_diags)
    # Should not have pylint warning because pylint_odoo is false
    assert not any(d["rule"] == "adapter-pylint-odoo-warning" for d in all_diags)

    # 3. [adapters] ruff = false => no execution, no warnings
    (tmp_path / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    all_diags = []
    for m in data.get("modules", {}).values():
        all_diags.extend(m.get("diagnostics", []))
    assert not any(d["rule"].startswith("adapter-") for d in all_diags)
