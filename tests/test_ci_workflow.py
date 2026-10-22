"""The CI workflow keeps covering the platforms the extension is used on."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "ci.yml"
PUBLISH = WORKFLOWS / "publish.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _publish_jobs() -> dict:
    return yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))["jobs"]


def _commands(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in job["steps"])


def test_vscode_extension_is_built_on_linux_and_windows():
    job = _jobs()["vscode-extension"]
    assert job["runs-on"] == "${{ matrix.os }}"
    assert {"ubuntu-latest", "windows-latest"} <= set(job["strategy"]["matrix"]["os"])
    # one OS failing must not hide the other
    assert job["strategy"]["fail-fast"] is False


def test_language_server_tests_run_on_windows():
    job = _jobs()["lsp-windows"]
    assert job["runs-on"] == "windows-latest"
    commands = "\n".join(s.get("run", "") for s in job["steps"])
    assert "tests/lsp" in commands


def test_tests_run_on_every_declared_python():
    job = _jobs()["test"]
    assert {"3.10", "3.11", "3.12", "3.13"} <= set(
        job["strategy"]["matrix"]["python-version"]
    )


def test_lowest_supported_dependency_versions_are_tested_on_the_oldest_python():
    job = _jobs()["lowest-versions"]
    assert "--resolution lowest-direct" in _commands(job)
    assert "pytest" in _commands(job)
    pythons = [s.get("with", {}).get("python-version") for s in job["steps"]]
    assert "3.10" in pythons


def test_publish_waits_for_tests_version_check_and_smoke_test():
    jobs = _publish_jobs()
    assert {"check-version", "test", "build", "smoke-test", "pypi-publish"} <= set(jobs)
    assert {"check-version", "test", "smoke-test"} <= set(jobs["pypi-publish"]["needs"])
    assert "scripts/check_release_version.py" in _commands(jobs["check-version"])
    assert "pytest" in _commands(jobs["test"])
    assert "ruff check" in _commands(jobs["test"])
    smoke = _commands(jobs["smoke-test"])
    assert "--version" in smoke
    assert "scan" in smoke


def test_publish_keeps_trusted_publishing_on_the_publish_job_only():
    workflow = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    assert workflow.get("permissions") == {"contents": "read"}
    assert "id-token" not in workflow["permissions"]
    jobs = _publish_jobs()
    assert "build" in jobs["pypi-publish"]["needs"]
    publish = jobs["pypi-publish"]
    assert publish["permissions"]["id-token"] == "write"
    assert publish["environment"]["name"] == "pypi"
    assert not any(
        "id-token" in job.get("permissions", {})
        for name, job in jobs.items()
        if name != "pypi-publish"
    )
    uses = [s.get("uses", "") for s in publish["steps"]]
    assert "pypa/gh-action-pypi-publish@release/v1" in uses


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # YAML reads a bare `on` as True
    return data


def test_release_starts_only_from_a_version_bump_on_main():
    triggers = _workflow("release.yml")["on"]
    assert triggers["push"] == {"branches": ["main"], "paths": ["pyproject.toml"]}
    job = _workflow("release.yml")["jobs"]["tag"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    commands = _commands(job)
    # nothing is tagged before the version and the notes are known to be good
    assert commands.index("check_release_version.py") < commands.index("git tag")
    assert commands.index("changelog_notes.py") < commands.index("git tag")
    # a Release made with GITHUB_TOKEN triggers nothing, so publish.yml is dispatched
    assert "gh workflow run publish.yml --ref" in commands


def test_publish_builds_the_vsix_and_publishes_it_after_pypi():
    jobs = _publish_jobs()
    assert {"pypi-publish", "vsix"} <= set(jobs["github-release"]["needs"])
    assert {"pypi-publish", "vsix"} <= set(jobs["marketplace-publish"]["needs"])
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    # the token is a secret, never an argument
    assert "--pat" not in _commands(jobs["marketplace-publish"])
