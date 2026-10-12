"""The test suite must never reach the real `gh`: it would act as whoever is logged in.

`tests/conftest.py` puts a stub `gh` first on PATH for the whole session (child processes
included), after a SARIF scan commented on real pull requests from a developer's machine.
"""

from __future__ import annotations

import shutil
import subprocess


def test_gh_on_path_is_the_stub():
    found = shutil.which("gh")
    assert found is not None
    assert "gh-stub" in found


def test_the_stub_fails_like_gh_outside_a_pull_request():
    result = subprocess.run(
        ["gh", "pr", "view"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
