"""scan --history/--badge and the `history` command group."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app
from odoo_doctor.core.history import load_history

runner = CliRunner()


def _addon(root: Path, *, bad: bool) -> Path:
    mod = root / "addons" / "m"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        "{'name': 'M', 'version': '17.0.1.0.0', 'depends': ['base'], 'data': [], "
        "'installable': True, 'license': 'LGPL-3'}"
    )
    (mod / "x.py").write_text(
        'def f(self, name):\n    self.env.cr.execute(f"SELECT {name}")\n'
        if bad
        else "def f(self):\n    return 1\n"
    )
    (root / "odoo-doctor.toml").write_text(
        '[odoo-doctor]\nodoo_version = "17.0"\n'
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    return root / "addons"


def test_scan_appends_history_and_trend_flags_regression(tmp_path: Path):
    hist = tmp_path / "h.jsonl"
    addons = _addon(tmp_path, bad=False)
    ok = runner.invoke(app, ["scan", str(addons), "--history", str(hist)])
    assert ok.exit_code == 0
    _addon(tmp_path, bad=True)
    runner.invoke(app, ["scan", str(addons), "--history", str(hist)])

    records, skipped = load_history(hist)
    assert skipped == 0 and len(records) == 2
    assert records[0]["project"]["overall"] == 100.0
    assert records[1]["project"]["overall"] < 100.0
    assert records[1]["tool_version"]

    shown = runner.invoke(app, ["history", "show", str(hist)])
    assert shown.exit_code == 0 and "[REGRESSION] project" in shown.output
    gated = runner.invoke(app, ["history", "show", str(hist), "--max-drop", "1"])
    assert gated.exit_code == 2
    lenient = runner.invoke(app, ["history", "show", str(hist), "--max-drop", "99"])
    assert lenient.exit_code == 0


def test_scan_writes_svg_and_json_badges(tmp_path: Path):
    addons = _addon(tmp_path, bad=False)
    svg = tmp_path / "out" / "badge.svg"
    endpoint = tmp_path / "badge.json"
    result = runner.invoke(app, ["scan", str(addons), "--badge", str(svg), "--json"])
    assert result.exit_code == 0
    ET.fromstring(svg.read_text(encoding="utf-8"))
    runner.invoke(app, ["scan", str(addons), "--badge", str(endpoint)])
    assert json.loads(endpoint.read_text())["message"].startswith("100.0")


def test_history_and_badge_refuse_diff_scans(tmp_path: Path):
    addons = _addon(tmp_path, bad=False)
    result = runner.invoke(
        app, ["scan", str(addons), "--diff", "HEAD", "--history", str(tmp_path / "h")]
    )
    assert result.exit_code == 3
    assert not (tmp_path / "h").exists()


def test_import_legacy_v030_report(tmp_path: Path):
    legacy = tmp_path / "old.json"
    legacy.write_text(
        json.dumps(
            {
                "version": "0.3.0",
                "schema_version": "1.0",
                "project_score": {"overall": 88.0, "label": "Good", "module_count": 1},
                "modules": {"m": {"score": {"overall": 88.0, "label": "Good"}}},
            }
        )
    )
    hist = tmp_path / "h.jsonl"
    result = runner.invoke(
        app,
        ["history", "import", str(hist), str(legacy), "--branch", "main",
         "--timestamp", "2026-01-01T00:00:00Z"],
    )  # fmt: skip
    assert result.exit_code == 0 and "schema inferred as v1" in result.output
    (rec,), _ = load_history(hist)
    assert rec["score_schema_version"] == 1 and rec["branch"] == "main"
    assert rec["timestamp"] == "2026-01-01T00:00:00+00:00"

    shown = runner.invoke(app, ["history", "show", str(hist)])
    assert "v1*" in shown.output and "pre-0.4.0" in shown.output


def test_import_skips_bad_files_and_exits_3_if_nothing_imported(tmp_path: Path):
    junk = tmp_path / "junk.json"
    junk.write_text("not json")
    empty = tmp_path / "empty.json"
    empty.write_text('{"modules": {}}')
    result = runner.invoke(
        app, ["history", "import", str(tmp_path / "h.jsonl"), str(junk), str(empty)]
    )
    assert result.exit_code == 3
    assert not (tmp_path / "h.jsonl").exists()


def test_import_rejects_bad_timestamp(tmp_path: Path):
    result = runner.invoke(
        app,
        ["history", "import", str(tmp_path / "h"), str(tmp_path / "r"),
         "--timestamp", "yesterday"],
    )  # fmt: skip
    assert result.exit_code == 3


def test_show_on_missing_file(tmp_path: Path):
    result = runner.invoke(app, ["history", "show", str(tmp_path / "none.jsonl")])
    assert result.exit_code == 0 and "No history records" in result.output


def test_history_refuses_partial_module_scans(tmp_path: Path):
    addons = _addon(tmp_path, bad=False)
    hist = tmp_path / "h.jsonl"
    via_flag = runner.invoke(
        app, ["scan", str(addons), "--module", "m", "--history", str(hist)]
    )
    assert via_flag.exit_code == 3 and not hist.exists()
    with (tmp_path / "odoo-doctor.toml").open("a") as fh:
        fh.write("\n")
    cfg = (tmp_path / "odoo-doctor.toml").read_text()
    (tmp_path / "odoo-doctor.toml").write_text(
        cfg.replace("[odoo-doctor]\n", '[odoo-doctor]\ntarget_modules = ["m"]\n')
    )
    via_cfg = runner.invoke(
        app, ["scan", str(addons), "--badge", str(tmp_path / "b.svg")]
    )
    assert via_cfg.exit_code == 3 and not (tmp_path / "b.svg").exists()
