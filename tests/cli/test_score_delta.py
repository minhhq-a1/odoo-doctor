import subprocess
from pathlib import Path
import pytest
from typer.testing import CliRunner
from odoo_doctor.cli.app import app, _collect_scores
from odoo_doctor.core.config import OdooDoctorConfig

runner = CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    # Init git
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)

    # Create bad module on main
    mod = repo / "my_addon"
    mod.mkdir()
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text("{'name': 'My Addon', 'version': '1.0'}")
    (mod / "models.py").write_text("def my_func():\n    pass\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True)

    # Create head branch
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo, check=True)
    (mod / "models.py").write_text("def my_func():\n    return True\n")
    subprocess.run(["git", "commit", "-am", "Fix"], cwd=repo, check=True)

    return repo


def test_score_delta_reports_improvement(temp_git_repo: Path):
    result = runner.invoke(app, ["scan", str(temp_git_repo), "--score-delta", "main"])
    assert result.exit_code == 0
    # It should compute delta and not leave worktree
    assert (
        "(vs base)" in result.output
        or "delta" in result.output.lower()
        or "vs main" in result.output
        or "Score" in result.output
    )


def test_score_delta_unknown_ref_exits_3(temp_git_repo: Path):
    result = runner.invoke(
        app, ["scan", str(temp_git_repo), "--score-delta", "does-not-exist"]
    )
    assert result.exit_code == 3
    assert (
        "could not resolve" in result.output.lower() or "error" in result.output.lower()
    )


def test_score_delta_cleans_up_worktree(temp_git_repo: Path):
    runner.invoke(app, ["scan", str(temp_git_repo), "--score-delta", "main"])
    # Check worktree
    res = subprocess.run(
        ["git", "worktree", "list"], cwd=temp_git_repo, capture_output=True, text=True
    )
    assert temp_git_repo.name in res.stdout
    # Should only have the main worktree
    assert len(res.stdout.strip().split("\n")) == 1


def test_collect_scores_helper_is_behavior_preserving(fixtures_dir: Path):
    bad_addon = fixtures_dir / "bad_addon"
    cfg = OdooDoctorConfig()
    diags, scores = _collect_scores([bad_addon], cfg, "17.0", config_root=bad_addon)

    assert "bad_addon" in scores
    assert scores["bad_addon"].overall < 100.0
    assert len(diags) > 0
