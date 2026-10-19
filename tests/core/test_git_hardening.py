"""git runs against the scanned repo, so a hostile `.git/config` or hook must not run code.

The fixtures are inert: a script that only creates a marker file under tmp_path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import _get_changed_files, app
from odoo_doctor.core.history import git_info

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the hostile scripts are POSIX shell"
)

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
    (mod / "models.py").write_text("def f():\n    return 1\n")
    _git(repo, "commit", "-qam", "second")
    return repo


def _marker_script(tmp_path: Path) -> tuple[Path, Path]:
    marker = tmp_path / "marker"
    script = tmp_path / "hostile.sh"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    script.chmod(0o755)
    return script, marker


def test_hostile_fsmonitor_does_not_run_for_git_info(repo: Path, tmp_path: Path):
    script, marker = _marker_script(tmp_path)
    _git(repo, "config", "core.fsmonitor", str(script))
    info = git_info(repo)
    assert info["dirty"] is False  # the normal answer is unchanged
    assert not marker.exists()


def test_hostile_fsmonitor_does_not_run_for_diff(repo: Path, tmp_path: Path):
    script, marker = _marker_script(tmp_path)
    _git(repo, "config", "core.fsmonitor", str(script))
    changed = _get_changed_files(repo, "HEAD~1")
    assert changed == {str((repo / "my_addon" / "models.py").resolve())}
    assert not marker.exists()


def test_hostile_hook_does_not_run_for_score_delta(repo: Path, tmp_path: Path):
    script, marker = _marker_script(tmp_path)
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(script.read_text())
    hook.chmod(0o755)
    result = runner.invoke(app, ["scan", str(repo), "--score-delta", "HEAD~1"])
    assert result.exit_code == 0, result.output
    assert not marker.exists()


def test_hostile_hooks_path_does_not_run_for_score_delta(repo: Path, tmp_path: Path):
    script, marker = _marker_script(tmp_path)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "post-checkout").write_text(script.read_text())
    (hooks / "post-checkout").chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))
    result = runner.invoke(app, ["scan", str(repo), "--score-delta", "HEAD~1"])
    assert result.exit_code == 0, result.output
    assert not marker.exists()


def test_run_git_command_line_and_environment(repo: Path, monkeypatch):
    from odoo_doctor.core import git as gitmod

    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(cmd=cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setattr(gitmod.subprocess, "run", fake_run)
    gitmod.run_git(["diff", "--name-only", "HEAD"], cwd=repo)
    cmd, env = seen["cmd"], seen["env"]
    assert cmd[0] == "git"
    for flag in ("core.fsmonitor=false", "core.sshCommand="):
        assert flag in cmd
    assert any(a.startswith("core.hooksPath=") for a in cmd)
    assert "--no-optional-locks" in cmd
    assert cmd[-3:] == ["diff", "--name-only", "HEAD"]
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "GITHUB_TOKEN" not in env and "GIT_DIR" not in env
    assert seen["cwd"] == repo


def test_diff_disables_external_diff_and_textconv(repo: Path, monkeypatch):
    from odoo_doctor.core import git as gitmod

    cmds = []
    real_run = subprocess.run

    def spy(cmd, **kwargs):
        cmds.append(cmd)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(gitmod.subprocess, "run", spy)
    assert _get_changed_files(repo, "HEAD~1")
    diff = next(c for c in cmds if "diff" in c)
    assert "--no-ext-diff" in diff and "--no-textconv" in diff


def _hostile_filter(repo: Path, tmp_path: Path, kind: str) -> Path:
    script, marker = _marker_script(tmp_path)
    script.write_text(script.read_text() + "cat\n")
    (repo / ".gitattributes").write_text("*.py filter=evil\n")
    _git(repo, "config", f"filter.evil.{kind}", str(script))
    return marker


def test_hostile_smudge_filter_does_not_run_for_score_delta(repo: Path, tmp_path: Path):
    marker = _hostile_filter(repo, tmp_path, "smudge")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attrs")
    marker.unlink(missing_ok=True)
    result = runner.invoke(app, ["scan", str(repo), "--score-delta", "HEAD"])
    assert result.exit_code == 0, result.output
    assert not marker.exists()


def test_hostile_clean_filter_does_not_run_for_git_info(repo: Path, tmp_path: Path):
    marker = _hostile_filter(repo, tmp_path, "clean")
    marker.unlink(missing_ok=True)
    (repo / "my_addon" / "models.py").write_text("def f():\n    return 2\n")
    assert git_info(repo)["dirty"] is True
    assert not marker.exists()
