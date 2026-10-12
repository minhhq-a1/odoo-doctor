"""Shared test fixtures for odoo-doctor."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# The golden corpus holds sample addons (including files named test_*.py that
# import `odoo`); they are scan inputs, never tests to collect.
collect_ignore = ["corpus"]


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_addon"


@pytest.fixture
def bad_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "bad_addon"


@pytest.fixture(scope="session", autouse=True)
def _no_real_gh(tmp_path_factory) -> Iterator[None]:
    """Put a stub `gh` first on PATH so no test can act as the developer's GitHub login.

    `scan --format github` shells out to `gh pr view` / `gh pr comment`; on a machine
    where `gh` is logged in that comments on the PR of the current checkout. The stub
    fails like `gh` does outside a pull request, so the code under test takes its
    "nothing to do" path. Child processes inherit PATH, so they are covered too.
    """
    stub_dir = tmp_path_factory.mktemp("gh-stub")
    stub = stub_dir / "gh"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == "nt":
        (stub_dir / "gh.cmd").write_text("@exit /b 1\n")
    saved = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{stub_dir}{os.pathsep}{saved}"
    try:
        yield
    finally:
        os.environ["PATH"] = saved
