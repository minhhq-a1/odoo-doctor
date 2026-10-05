"""Tests that need a directory inside the workspace (the sandbox only allows writes there)
must remove it again, otherwise `.tmp/` grows with every run."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_TMP = ROOT / ".tmp"


def _entries() -> set[str]:
    return set(os.listdir(WORKSPACE_TMP)) if WORKSPACE_TMP.exists() else set()


def test_fix_command_tests_leave_nothing_in_the_workspace_tmp():
    before = _entries()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/cli/test_fix_command.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _entries() - before == set()
