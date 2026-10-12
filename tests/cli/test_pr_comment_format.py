"""Only `--format github` posts the sticky PR comment; every other format leaves the PR alone.

The posting block once sat inside the `--format sarif` branch: a SARIF scan commented on
whatever pull request the current checkout had (the test suite did it for real), while
`--format github`, the one the Action runs, never did.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


@pytest.fixture
def posted(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        "odoo_doctor.reporters.pr_comment.post_pr_comment", calls.append
    )
    return calls


def _addon(tmp_path: Path) -> Path:
    addon = tmp_path / "my_addon"
    addon.mkdir()
    (addon / "__init__.py").write_text("")
    (addon / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '17.0.1.0.0', 'depends': ['base'], "
        "'data': [], 'license': 'LGPL-3'}"
    )
    return tmp_path


def test_github_format_posts_the_comment_once(tmp_path: Path, posted):
    result = runner.invoke(app, ["scan", str(_addon(tmp_path)), "--format", "github"])
    assert result.exit_code == 0
    assert len(posted) == 1
    assert posted[0].startswith("<!-- odoo-doctor -->")
    assert "Odoo Doctor Report" in posted[0]


@pytest.mark.parametrize("fmt", ["sarif", "json", "terminal"])
def test_other_formats_never_post(tmp_path: Path, posted, fmt):
    result = runner.invoke(app, ["scan", str(_addon(tmp_path)), "--format", fmt])
    assert result.exit_code == 0
    assert posted == []


def test_the_json_flag_never_posts(tmp_path: Path, posted):
    result = runner.invoke(app, ["scan", str(_addon(tmp_path)), "--json"])
    assert result.exit_code == 0
    assert posted == []


def test_no_pr_comment_keeps_github_annotations_but_does_not_post(
    tmp_path: Path, posted
):
    result = runner.invoke(
        app,
        ["scan", str(_addon(tmp_path)), "--format", "github", "--no-pr-comment"],
    )
    assert result.exit_code == 0
    assert posted == []
