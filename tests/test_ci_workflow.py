"""The CI workflow keeps covering the platforms the extension is used on."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


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
