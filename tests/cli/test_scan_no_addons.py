"""`scan` says so when it finds no addon: a path that holds no addon directly is not a clean project."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

MANIFEST = repr(
    {
        "name": "M",
        "version": "17.0.1.0.0",
        "depends": [],
        "data": [],
        "license": "LGPL-3",
    }
)
CONFIG = '[odoo-doctor]\nodoo_version = "17.0"\n\n[adapters]\nruff = false\npylint_odoo = false\n'
WARNING = "No Odoo addon found"


def _addon(parent: Path, name: str = "mod") -> None:
    addon = parent / name
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text(MANIFEST)
    (addon / "__init__.py").write_text("")


def _scan(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """The real command in a real process, so stdout and stderr stay separate."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_doctor.cli.app import app; app()",
            "scan",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _module_count(result: subprocess.CompletedProcess) -> int:
    return json.loads(result.stdout)["project_score"]["module_count"]


def test_a_path_whose_addons_sit_one_level_too_deep_gets_a_warning(tmp_path: Path):
    # the Odoo source layout: addons live in tmp/addons/<module>, not in tmp/<module>
    _addon(tmp_path / "addons")
    (tmp_path / "odoo-doctor.toml").write_text(CONFIG)

    result = _scan(tmp_path, str(tmp_path), "--json")

    assert result.returncode == 0  # a warning, not a failure
    assert _module_count(result) == 0
    assert WARNING in result.stderr
    assert str(tmp_path) in result.stderr  # says what was scanned
    assert "omit PATH" in result.stderr and "addons_paths" in result.stderr
    assert WARNING not in result.stdout  # stdout stays machine-readable


def test_a_folder_with_no_addon_at_all_gets_a_warning(tmp_path: Path):
    result = _scan(tmp_path, str(tmp_path), "--json")
    assert result.returncode == 0
    assert _module_count(result) == 0
    assert result.stderr.count(WARNING) == 1


def test_the_warning_is_not_mixed_into_terminal_output(tmp_path: Path):
    result = _scan(tmp_path, str(tmp_path))
    assert result.returncode == 0
    assert WARNING in result.stderr
    assert WARNING not in result.stdout


def test_config_addons_paths_without_a_path_finds_the_addons_silently(tmp_path: Path):
    _addon(tmp_path / "addons")
    (tmp_path / "odoo-doctor.toml").write_text(
        CONFIG.replace(
            'odoo_version = "17.0"', 'odoo_version = "17.0"\naddons_paths = ["addons"]'
        )
    )

    result = _scan(tmp_path, "--json")  # no PATH: use addons_paths

    assert result.returncode == 0
    assert _module_count(result) == 1
    assert WARNING not in result.stderr


@pytest.mark.parametrize("layout", ["direct", "single"])
def test_a_path_that_holds_addons_is_silent(tmp_path: Path, layout: str):
    if layout == "direct":
        _addon(tmp_path)  # tmp/mod
        target = tmp_path
    else:
        _addon(tmp_path, "solo")
        target = tmp_path / "solo"  # the addon itself
    (tmp_path / "odoo-doctor.toml").write_text(CONFIG)

    result = _scan(tmp_path, str(target), "--json")

    assert result.returncode == 0
    assert _module_count(result) == 1
    assert WARNING not in result.stderr


def test_a_diff_scan_with_nothing_changed_is_not_a_missing_addon(tmp_path: Path):
    _addon(tmp_path)
    (tmp_path / "odoo-doctor.toml").write_text(CONFIG)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    for command in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "x"],
    ):
        subprocess.run([*git, *command], cwd=tmp_path, check=True, capture_output=True)

    result = _scan(tmp_path, str(tmp_path), "--diff", "HEAD", "--json")

    assert result.returncode == 0
    assert WARNING not in result.stderr  # the addon exists, only nothing changed
