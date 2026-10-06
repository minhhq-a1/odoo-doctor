"""CI templates (GitLab CI, Bitbucket Pipelines): valid YAML, real flags, and the script runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import typer.main
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "ci-templates"
FIXTURES = ROOT / "tests" / "fixtures"


def _gitlab() -> dict:
    return yaml.safe_load((TEMPLATES / "gitlab-ci.yml").read_text(encoding="utf-8"))


def _bitbucket() -> dict:
    return yaml.safe_load(
        (TEMPLATES / "bitbucket-pipelines.yml").read_text(encoding="utf-8")
    )


def _bitbucket_step() -> dict:
    return _bitbucket()["definitions"]["steps"][0]["step"]


def _gitlab_script() -> str:
    return "\n".join(_gitlab()["odoo-doctor"]["script"])


def _bitbucket_script() -> str:
    # The first item installs odoo-doctor; tests run against the checkout under test.
    items = [i for i in _bitbucket_step()["script"] if not i.startswith("pip install")]
    return "\n".join(items)


SCRIPTS = {"gitlab": _gitlab_script, "bitbucket": _bitbucket_script}
TARGET_VAR = {
    "gitlab": "CI_MERGE_REQUEST_TARGET_BRANCH_NAME",
    "bitbucket": "BITBUCKET_PR_DESTINATION_BRANCH",
}


# --- structure ---------------------------------------------------------------


def test_gitlab_job_shape():
    job = _gitlab()["odoo-doctor"]
    assert job["stage"] == "test"
    assert job["variables"]["GIT_DEPTH"] == "0"  # the merge base needs history
    assert any("merge_request_event" in r["if"] for r in job["rules"])
    assert any("CI_DEFAULT_BRANCH" in r["if"] for r in job["rules"])
    assert "odoo-doctor-report.json" in job["artifacts"]["paths"]
    assert job["artifacts"]["when"] == "always"
    assert any("pip install" in line for line in job["before_script"])


def test_gitlab_declares_documented_variables():
    declared = set(_gitlab()["variables"])
    assert declared == {
        "ODOO_DOCTOR_VERSION",
        "ODOO_DOCTOR_PATHS",
        "ODOO_DOCTOR_ODOO_VERSION",
        "ODOO_DOCTOR_FAIL_ON",
        "ODOO_DOCTOR_MIN_SCORE",
        "ODOO_DOCTOR_ADVISORY",
    }


def test_bitbucket_pipeline_shape():
    step = _bitbucket_step()
    assert step["clone"]["depth"] == "full"
    assert step["artifacts"] == ["odoo-doctor-report.json"]
    prs = _bitbucket()["pipelines"]["pull-requests"]["**"]
    assert prs[0]["step"]["name"] == step["name"]  # the anchor is really used


# --- the shell is valid and uses real CLI flags ------------------------------


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_script_is_valid_posix_shell(which):
    result = subprocess.run(
        ["sh", "-n"],
        input=SCRIPTS[which](),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_script_only_uses_flags_that_scan_accepts(which):
    import odoo_doctor.cli.app  # noqa: F401
    from odoo_doctor.cli.app import app

    scan = typer.main.get_command(app).commands["scan"]
    known = {opt for p in scan.params for opt in p.opts}
    # Only the lines that build or run the scan command (git and pip have own flags).
    scan_lines = [
        line
        for line in SCRIPTS[which]().splitlines()
        if "odoo-doctor scan" in line or line.strip().startswith('set -- "$@"')
    ]
    used = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", "\n".join(scan_lines)))
    assert used, "the script passes no flags at all"
    assert used <= known, f"unknown scan flags: {sorted(used - known)}"


# --- the script behaves ------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def _make_repo(tmp_path: Path) -> Path:
    """A clone of an `origin` whose main holds a clean and a bad addon."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    shutil.copytree(FIXTURES / "sample_addon", work / "good_addon")
    shutil.copytree(FIXTURES / "bad_addon", work / "bad_addon")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "origin", "main")
    return work


def _run(which: str, cwd: Path, **env: str):
    if shutil.which("odoo-doctor") is None:
        pytest.skip("odoo-doctor is not on PATH")
    clean = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ODOO_DOCTOR_", "CI_", "BITBUCKET_"))
    }
    return subprocess.run(
        ["sh", "-c", SCRIPTS[which]()],
        cwd=cwd,
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_branch_pipeline_scans_everything_and_fails_on_errors(which, tmp_path):
    work = _make_repo(tmp_path)
    result = _run(which, work)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((work / "odoo-doctor-report.json").read_text())
    assert {"bad_addon", "good_addon"} <= set(report["modules"])


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_advisory_mode_never_fails(which, tmp_path):
    work = _make_repo(tmp_path)
    result = _run(which, work, ODOO_DOCTOR_ADVISORY="true")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (work / "odoo-doctor-report.json").exists()


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_merge_request_scans_only_changed_files(which, tmp_path):
    work = _make_repo(tmp_path)
    _git(work, "checkout", "-b", "feature")
    manifest = work / "good_addon" / "__manifest__.py"
    manifest.write_text(manifest.read_text() + "\n# touched\n")
    _git(work, "commit", "-am", "touch the clean addon only")
    # The target branch moves on after the branch point: its changes must not
    # leak into the MR scan (the reason the script diffs against the merge base).
    _git(work, "checkout", "main")
    other = work / "bad_addon" / "__manifest__.py"
    other.write_text(other.read_text() + "\n# main moved on\n")
    _git(work, "commit", "-am", "main moves on")
    _git(work, "push", "origin", "main")
    _git(work, "checkout", "feature")

    result = _run(which, work, **{TARGET_VAR[which]: "main"})

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((work / "odoo-doctor-report.json").read_text())
    # An addon the MR did not touch is listed but not scanned: no findings at all.
    assert report["modules"]["bad_addon"]["diagnostics"] == []


@pytest.mark.parametrize("which", sorted(SCRIPTS))
def test_merge_request_touching_the_bad_addon_fails(which, tmp_path):
    work = _make_repo(tmp_path)
    _git(work, "checkout", "-b", "feature")
    for path in (work / "bad_addon").rglob("*.py"):
        path.write_text(path.read_text() + "\n# touched\n")
    _git(work, "commit", "-am", "touch the bad addon")

    result = _run(which, work, **{TARGET_VAR[which]: "main"})

    assert result.returncode == 1, result.stdout + result.stderr
