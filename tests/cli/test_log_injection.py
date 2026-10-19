"""Repo-derived names in warning and error lines cannot start a CI workflow command.

GitHub treats a log line that starts with `::` as a command. A name holding a newline and
`::error::` must therefore never produce an output line starting with `::`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app
from odoo_doctor.rules.registry import default_registry

runner = CliRunner()

HOSTILE = "a\n::error::INJECTED"
MANIFEST = "{'name': 'M', 'version': '%s', 'depends': ['base'], 'data': []}"
CONFIG = "[adapters]\nruff = false\npylint_odoo = false\n"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="a newline in a file name needs POSIX"
)


def _no_injection(*streams: str) -> None:
    for stream in streams:
        for line in stream.splitlines():
            assert not line.lstrip().startswith("::"), line
        assert "\n::" not in stream


def _addon(root: Path, name: str, version: str = "17.0.1.0.0") -> Path:
    mod = root / name
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(MANIFEST % version)
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import good\n")
    (mod / "models" / "good.py").write_text("def f(x):\n    return eval(x)\n")
    (root / "odoo-doctor.toml").write_text(CONFIG)
    return mod


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no os.mkfifo")
def test_skipped_file_warning(tmp_path: Path):
    mod = _addon(tmp_path, "mod")
    os.mkfifo(mod / "models" / f"{HOSTILE}.py")
    code = "from odoo_doctor.cli.app import app; app()"
    proc = subprocess.run(
        [sys.executable, "-c", code, "scan", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert "[WARN] skipped" in proc.stderr
    _no_injection(proc.stderr, proc.stdout)


def test_module_failure_line(tmp_path: Path):
    _addon(tmp_path, HOSTILE)
    result = runner.invoke(app, ["scan", str(tmp_path), "--min-score", "100"])
    assert "[FAIL]" in result.stderr
    _no_injection(result.stderr, result.stdout)


def test_rule_crash_warnings(tmp_path: Path, monkeypatch):
    _addon(tmp_path, HOSTILE)

    def boom(*_a, **_k):
        raise RuntimeError("x\n::error::EXC")

    patched = [
        (m, boom) if m.name in ("eval-usage", "unbounded-search") else (m, f)
        for m, f in default_registry._rules
    ]
    monkeypatch.setattr(default_registry, "_rules", patched)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert "crashed on" in result.stderr
    _no_injection(result.stderr, result.stdout)


def test_diff_and_score_delta_messages(tmp_path: Path):
    _addon(tmp_path, "mod")
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
        ["add", "."],
        ["commit", "-qm", "i"],
    ):
        _git(tmp_path, *cmd)
    ref = "no\n::error::REF"
    for flag in ("--diff", "--score-delta"):
        result = runner.invoke(app, ["scan", str(tmp_path), flag, ref])
        assert result.exit_code == 3, result.output
        _no_injection(result.stderr, result.stdout)
    result = runner.invoke(app, ["scan", str(tmp_path), "--diff=-\n::error::x"])
    _no_injection(result.stderr, result.stdout)


def test_upgrade_report_warning(tmp_path: Path):
    _addon(tmp_path, HOSTILE, version="16.0.1.0.0")
    result = runner.invoke(app, ["scan", str(tmp_path), "--upgrade-report"])
    assert "--upgrade-report" in result.stderr
    _no_injection(result.stderr, result.stdout)


def test_fix_diff_header(tmp_path: Path):
    mod = _addon(tmp_path, HOSTILE)
    (mod / "__manifest__.py").write_text(
        "{\n    'name': 'M',\n    'version': '17.0.1.0.0',\n    'depends': ['base'],\n"
        "    'data': [],\n    'installable': True,\n}\n"
    )
    result = runner.invoke(app, ["fix", str(tmp_path), "--fix-dry-run"])
    _no_injection(result.stderr, result.stdout)


def test_history_lines(tmp_path: Path):
    bad = tmp_path / "h\n::error::x.jsonl"
    bad.write_text("not json\n")
    result = runner.invoke(app, ["history", "show", str(bad)])
    assert "unreadable line" in result.stderr, result.output
    _no_injection(result.stderr, result.stdout)
    report = tmp_path / "r\n::error::y.json"
    report.write_text("{}")
    result = runner.invoke(app, ["history", "import", str(bad), str(report)])
    assert "[WARN]" in result.stderr, result.output
    _no_injection(result.stderr, result.stdout)
