"""scan --show-low and [surfaces.terminal]: what the terminal lists vs the data."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG = '[odoo-doctor]\nodoo_version = "17.0"\n[adapters]\nruff = false\npylint_odoo = false\n'


def _project(root: Path, *, config: str | None = CONFIG, with_sql: bool = True) -> Path:
    """One addon with a low-confidence finding (.sudo()) and, optionally, a high one."""
    mod = root / "addons" / "m"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        "{'name': 'M', 'version': '17.0.1.0.0', 'depends': ['base'], 'data': [], "
        "'installable': True, 'license': 'LGPL-3'}"
    )
    (mod / "x.py").write_text(
        "from odoo import models\n\n\n"
        "class P(models.Model):\n"
        '    _inherit = "res.partner"\n\n'
        "    def f(self, name):\n"
        + ('        self.env.cr.execute(f"SELECT {name}")\n' if with_sql else "")
        + '        return self.env["res.users"].sudo().search([])\n'
    )
    if config is not None:
        (root / "odoo-doctor.toml").write_text(config)
    return root / "addons"


def _scan(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_doctor.cli.app import app; app()",
            "scan",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _plain(text: str) -> str:
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", text).split())


def _count_low(root: Path, addons: Path, *extra: str) -> int:
    done = _scan(root, str(addons), "--json", *extra)
    assert done.returncode in (0, 1), done.stderr
    report = json.loads(done.stdout)
    return sum(
        1
        for m in report["modules"].values()
        for d in m["diagnostics"]
        if d["confidence"] == "low"
    )


def test_default_hides_low_and_says_how_many(tmp_path: Path):
    addons = _project(tmp_path)
    lows = _count_low(tmp_path, addons)
    assert lows >= 1  # the fixture really produces a low-confidence finding
    out = _plain(_scan(tmp_path, str(addons)).stdout)
    assert "[low]" not in out
    assert f"{lows} finding(s) hidden by [surfaces.terminal]" in out


def test_show_low_lists_every_low_finding_and_no_footer(tmp_path: Path):
    addons = _project(tmp_path)
    lows = _count_low(tmp_path, addons)
    out = _plain(_scan(tmp_path, str(addons), "--show-low").stdout)
    assert out.count("[low]") == lows
    assert "hidden by" not in out


def test_hiding_works_without_any_config_file(tmp_path: Path):
    addons = _project(tmp_path, config=None)
    base = ("--odoo-version", "17.0")
    lows = _count_low(tmp_path, addons, *base)
    assert lows >= 1
    out = _plain(_scan(tmp_path, str(addons), *base).stdout)
    assert "[low]" not in out and f"{lows} finding(s) hidden by" in out


def _findings(root: Path, addons: Path, *extra: str) -> list[dict]:
    done = _scan(root, str(addons), "--json", *extra)
    assert done.returncode in (0, 1), done.stderr
    return [
        d for m in json.loads(done.stdout)["modules"].values() for d in m["diagnostics"]
    ]


def test_show_low_prints_every_finding_and_default_prints_the_non_low_ones(
    tmp_path: Path,
):
    """The printed set is the JSON set (rich wraps the `path:line` header, so the
    findings are matched through their message, which is printed on its own line)."""
    addons = _project(tmp_path)
    findings = _findings(tmp_path, addons)
    assert any(d["confidence"] == "low" for d in findings)
    assert any(d["confidence"] != "low" for d in findings)
    everything = _plain(_scan(tmp_path, str(addons), "--show-low").stdout)
    default = _plain(_scan(tmp_path, str(addons)).stdout)
    for message in {d["message"] for d in findings}:
        same = [d for d in findings if d["message"] == message]
        assert everything.count(" ".join(message.split())) == len(same), message
        shown = [d for d in same if d["confidence"] != "low"]
        assert default.count(" ".join(message.split())) == len(shown), message


def test_findings_hidden_by_the_terminal_still_fail_the_ci_gate(tmp_path: Path):
    """Only a low-confidence finding exists; [surfaces.ci_failure] admits it."""
    addons = _project(
        tmp_path,
        config=CONFIG + '[surfaces.ci_failure]\nmin_confidence = "low"\n',
        with_sql=False,
    )
    findings = _findings(tmp_path, addons)
    assert findings and all(d["confidence"] == "low" for d in findings)
    # use the lowest threshold the sudo finding's severity reaches
    threshold = "error" if findings[0]["severity"] == "error" else "warning"
    done = _scan(tmp_path, str(addons), "--fail-on", threshold)
    assert done.returncode == 1, done.stderr
    out = _plain(done.stdout)
    assert "[low]" not in out and "hidden by [surfaces.terminal]" in out


def test_config_can_show_everything(tmp_path: Path):
    addons = _project(
        tmp_path, config=CONFIG + '[surfaces.terminal]\nmin_confidence = "low"\n'
    )
    lows = _count_low(tmp_path, addons)
    out = _plain(_scan(tmp_path, str(addons)).stdout)
    assert out.count("[low]") == lows and "hidden by" not in out


def test_show_low_changes_nothing_but_the_terminal(tmp_path: Path):
    addons = _project(tmp_path)
    plain = _scan(tmp_path, str(addons), "--json")
    flagged = _scan(tmp_path, str(addons), "--json", "--show-low")
    assert plain.stdout == flagged.stdout
    sarif = _scan(tmp_path, str(addons), "--format", "sarif")
    sarif_flagged = _scan(tmp_path, str(addons), "--format", "sarif", "--show-low")
    assert sarif.stdout == sarif_flagged.stdout
    assert (
        _scan(tmp_path, str(addons), "--fail-on", "warning").returncode
        == _scan(tmp_path, str(addons), "--fail-on", "warning", "--show-low").returncode
    )
