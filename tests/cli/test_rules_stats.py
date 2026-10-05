"""`odoo-doctor rules stats`, the JSON key and the scan hint."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()
RULE = "raw-sql-string-interpolation"
_IGNORE_RULE = '[ignore]\nrules = ["raw-sql-string-interpolation"]\n'


def _write_module(root: Path, suppressed: int, surfaced: int) -> None:
    mod = root / "mod"
    (mod / "models").mkdir(parents=True, exist_ok=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    lines = [
        "from odoo import models\n\n",
        "class M(models.Model):\n",
        "    _name = 'mod.m'\n",
        "    _description = 'M'\n\n",
        "    def run(self, name):\n",
    ]
    for i in range(suppressed):
        lines.append("        # odoo-doctor: disable=raw-sql-string-interpolation\n")
        lines.append(
            f"        self.env.cr.execute(f\"SELECT {i} FROM t WHERE n = '{{name}}'\")\n"
        )
    for j in range(surfaced):
        lines.append(
            f'        self.env.cr.execute(f"SELECT {suppressed + j} FROM t '
            "WHERE n = '{name}'\")\n"
        )
    lines.append("        return None\n")
    (mod / "models" / "m.py").write_text("".join(lines))


def _addon(root: Path, suppressed: int, surfaced: int, toml_extra: str = "") -> Path:
    (root / "odoo-doctor.toml").write_text(
        '[odoo-doctor]\nodoo_version = "17.0"\n\n'
        "[adapters]\nruff = false\npylint_odoo = false\n\n" + toml_extra
    )
    _write_module(root, suppressed, surfaced)
    return root


def _stats_json(root: Path) -> dict:
    result = runner.invoke(app, ["rules", "stats", "--path", str(root), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _row(data: dict) -> dict:
    return next(r for r in data["rules"] if r["rule"] == RULE)


def test_stats_json_has_a_row_per_rule(tmp_path: Path):
    root = _addon(tmp_path, suppressed=2, surfaced=1)
    row = _row(_stats_json(root))
    assert (row["surfaced"], row["inline"]) == (1, 2)
    assert row["ignore_rule"] == 0 and row["severity_off"] == 0
    assert row["total"] == 3
    assert row["noisy"] is False


def test_noisy_rule_gets_a_suggestion(tmp_path: Path):
    root = _addon(tmp_path, suppressed=10, surfaced=2)
    row = _row(_stats_json(root))
    assert row["noisy"] is True
    assert "info" in row["suggestion"]

    table = runner.invoke(app, ["rules", "stats", "--path", str(root)])
    assert table.exit_code == 0
    assert RULE in table.stdout
    assert "noisy" in table.stdout
    assert "[severity]" in table.stdout


def test_rule_disabled_in_config_is_noisy_but_not_actionable(tmp_path: Path):
    root = _addon(tmp_path, suppressed=0, surfaced=10, toml_extra=_IGNORE_RULE)
    row = _row(_stats_json(root))
    assert row["ignore_rule"] == 10 and row["surfaced"] == 0
    assert row["noisy"] is True
    assert row["suggestion"] is None

    scan = runner.invoke(app, ["scan", str(root)])
    assert "look noisy" not in scan.stdout


def test_scan_prints_a_hint_for_an_actionable_noisy_rule(tmp_path: Path):
    root = _addon(tmp_path, suppressed=10, surfaced=2)
    scan = runner.invoke(app, ["scan", str(root)])
    assert "1 rule(s) look noisy" in scan.stdout
    assert "rules stats" in scan.stdout


def test_scan_json_has_suppression_stats_and_keeps_existing_keys(tmp_path: Path):
    root = _addon(tmp_path, suppressed=2, surfaced=1)
    result = runner.invoke(app, ["scan", str(root), "--json"])
    report = json.loads(result.stdout)
    module = report["modules"]["mod"]
    assert module["suppression_stats"][RULE]["inline"] == 2
    assert {"score", "fix_priorities", "diagnostics"} <= set(module)
    assert report["schema_version"] == "1.0"


def test_stats_with_nothing_to_report(tmp_path: Path):
    # no addon at all: a module with zero raw-sql code would still have other findings
    (tmp_path / "odoo-doctor.toml").write_text('[odoo-doctor]\nodoo_version = "17.0"\n')
    result = runner.invoke(app, ["rules", "stats", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "No findings or suppressions recorded." in result.stdout


def test_baseline_keeps_stats(tmp_path: Path):
    root = _addon(tmp_path, suppressed=2, surfaced=1)
    baseline = tmp_path / "baseline.json"
    runner.invoke(app, ["scan", str(root), "--write-baseline", str(baseline)])
    _write_module(root, suppressed=2, surfaced=2)  # one new finding stays visible

    result = runner.invoke(
        app, ["scan", str(root), "--baseline", str(baseline), "--json"]
    )
    module = json.loads(result.stdout)["modules"]["mod"]
    counted = [d for d in module["diagnostics"] if d["rule"] == RULE]
    assert len(counted) == 1  # the pre-existing one is baselined away
    # surfaced counts findings before the baseline filter
    assert module["suppression_stats"][RULE]["surfaced"] == 2
    assert module["suppression_stats"][RULE]["inline"] == 2
