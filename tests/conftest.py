"""Shared test fixtures for odoo-doctor."""

from __future__ import annotations

import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_addon"


@pytest.fixture
def bad_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "bad_addon"
