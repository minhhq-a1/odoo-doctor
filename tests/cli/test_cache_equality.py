"""A ``--cache`` hit must print exactly what the live scan prints (scores included)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()

_MODEL = (
    "from odoo import models\n\n\nclass M(models.Model):\n    _name = 'x.m'\n\n"
    "    def go(self):\n        self.env.cr.commit()\n        return self.name_get()\n"
)
_TOML = "[adapters]\nruff = false\npylint_odoo = false\n"


def _addon(root: Path, name: str, series: str) -> None:
    mod = root / name
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        f"{{'name': '{name}', 'version': '{series}.1.0.0', 'depends': ['base'], "
        "'data': [], 'license': 'LGPL-3'}"
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    (mod / "models" / "m.py").write_text(_MODEL.replace("x.m", f"x.{name}"))


@pytest.fixture
def project(tmp_path: Path):
    def make(series: str) -> Path:
        root = tmp_path / series
        root.mkdir()
        (root / "odoo-doctor.toml").write_text(_TOML)
        # enough modules that a hash-ordered set cannot match the scan order by luck
        for name in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"):
            _addon(root, name, series)
        return root

    return make


def _scan(root: Path, *args: str) -> str:
    result = runner.invoke(app, ["scan", str(root), "--json", *args])
    assert result.exit_code in (0, 2), result.output
    return result.stdout


def _assert_hit_equals_live(root: Path, *args: str, nonempty: bool = True) -> None:
    uncached = _scan(root, *args)
    cold = _scan(root, *args, "--cache")
    warm = _scan(root, *args, "--cache")
    assert (root / ".odoo_doctor_cache").exists()
    assert cold == uncached
    assert warm == uncached
    if nonempty:
        assert json.loads(warm)["modules"]  # not vacuous


@pytest.mark.parametrize("series", ["17.0", "18.0", "19.0"])
def test_plain_scan(project, series):
    _assert_hit_equals_live(project(series))


@pytest.mark.parametrize(
    "flags",
    [
        ("--module", "alpha"),
        ("--odoo-version", "18.0"),
        ("--upgrade-report",),
        ("--upgrade-report", "--odoo-version", "19.0"),  # forced target
    ],
)
def test_flags(project, flags):
    _assert_hit_equals_live(project("17.0"), *flags)


def test_baseline(project, tmp_path):
    root = project("17.0")
    baseline = tmp_path / "baseline.json"
    runner.invoke(app, ["scan", str(root), "--write-baseline", str(baseline)])
    _assert_hit_equals_live(root, "--baseline", str(baseline), nonempty=False)
    # a baseline that hides only some findings
    data = json.loads(baseline.read_text())
    ids = data["ids"] if isinstance(data, dict) and "ids" in data else data
    if isinstance(ids, list) and len(ids) > 1:
        baseline.write_text(json.dumps({**data, "ids": ids[:1]}))
        _assert_hit_equals_live(root, "--baseline", str(baseline))


def test_diff_ignores_the_cache(project):
    root = project("17.0")
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    (root / "alpha" / "models" / "m.py").write_text(_MODEL + "# changed\n")
    uncached = _scan(root, "--diff", "HEAD")
    assert _scan(root, "--diff", "HEAD", "--cache") == uncached
    assert _scan(root, "--diff", "HEAD", "--cache") == uncached
