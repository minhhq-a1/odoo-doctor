"""`--diff` must see every changed file name, and a ref must never act as a git option."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import _get_changed_files, app

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    mod = repo / "my_addon"
    mod.mkdir(parents=True)
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text("{'name': 'My Addon', 'version': '1.0'}")
    (mod / "models.py").write_text("def f():\n    pass\n")
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
        ["add", "."],
        ["commit", "-qm", "init"],
    ):
        _git(repo, *cmd)
    return repo


def test_changed_files_keeps_non_ascii_and_odd_names(repo: Path):
    mod = repo / "my_addon"
    names = ["modèle.py", "with space.py", "tab\there.py", "line\nbreak.py", "日本.py"]
    if sys.platform == "win32":  # NTFS cannot hold a tab or newline in a name
        names = names[:2] + names[4:]
    for name in names:
        (mod / name).write_text("x = 1\n")
    _git(repo, "add", ".")
    changed = _get_changed_files(repo, "HEAD")
    assert changed == {str((mod / n).resolve()) for n in names}


@pytest.mark.parametrize("ref", ["--output=OUT", "-p", "--no-index", "-"])
def test_diff_refuses_a_ref_that_looks_like_an_option(repo: Path, tmp_path: Path, ref):
    out = tmp_path / "written-by-git"
    ref = ref.replace("OUT", str(out))
    result = runner.invoke(app, ["scan", str(repo), f"--diff={ref}", "--json"])
    assert result.exit_code == 3
    assert "--diff" in result.output
    assert not out.exists()


def test_score_delta_refuses_a_ref_that_looks_like_an_option(repo: Path):
    result = runner.invoke(app, ["scan", str(repo), "--score-delta=--orphan"])
    assert result.exit_code == 3


def test_diff_still_accepts_ordinary_refs(repo: Path):
    (repo / "my_addon" / "models.py").write_text("def f():\n    return 1\n")
    result = runner.invoke(app, ["scan", str(repo), "--diff", "HEAD", "--json"])
    assert result.exit_code == 0
