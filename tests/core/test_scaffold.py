"""The plugin scaffold behind `odoo-doctor rules new`."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from odoo_doctor import __version__
from odoo_doctor.core.scaffold import (
    module_name,
    render_plugin_scaffold,
    validate_rule_name,
    write_scaffold,
)

NAME = "no-print-statements"


def test_scaffold_has_the_files_a_plugin_pack_needs():
    files = render_plugin_scaffold(NAME)
    assert set(files) == {
        "odoo-doctor-rules-no-print-statements/pyproject.toml",
        "odoo-doctor-rules-no-print-statements/README.md",
        "odoo-doctor-rules-no-print-statements/.gitignore",
        "odoo-doctor-rules-no-print-statements/src/odoo_doctor_rules_no_print_statements/__init__.py",
        "odoo-doctor-rules-no-print-statements/src/odoo_doctor_rules_no_print_statements/rules.py",
        "odoo-doctor-rules-no-print-statements/tests/test_no_print_statements.py",
    }


def test_pyproject_registers_the_entry_point_and_depends_on_odoo_doctor():
    pyproject = render_plugin_scaffold(NAME)[
        "odoo-doctor-rules-no-print-statements/pyproject.toml"
    ]
    assert 'name = "odoo-doctor-rules-no-print-statements"' in pyproject
    assert '[project.entry-points."odoo_doctor.rules"]' in pyproject
    assert (
        'no_print_statements = "odoo_doctor_rules_no_print_statements.rules"'
        in pyproject
    )
    assert f'"odoo-doctor>={__version__}"' in pyproject


def test_rule_module_declares_the_plugin_api_and_only_imports_the_public_surface():
    source = render_plugin_scaffold(NAME)[
        "odoo-doctor-rules-no-print-statements/src/"
        "odoo_doctor_rules_no_print_statements/rules.py"
    ]
    assert "ODOO_DOCTOR_PLUGIN_API = 1" in source
    assert f'name="{NAME}"' in source
    imports = re.findall(r"^(?:from|import) (odoo_doctor\S*)", source, re.MULTILINE)
    assert imports == ["odoo_doctor.plugin_api"]


def test_module_name_maps_a_rule_name_to_a_python_identifier():
    assert module_name("no-print-statements") == "no_print_statements"


@pytest.mark.parametrize(
    "bad", ["", "Bad", "has space", "-lead", "trail-", "double--dash", "1abc", "a_b"]
)
def test_invalid_rule_names_are_rejected(bad: str):
    with pytest.raises(ValueError):
        validate_rule_name(bad)


def test_an_existing_rule_name_is_rejected():
    import odoo_doctor.cli.app  # noqa: F401  (registers the built-in rules)

    with pytest.raises(ValueError, match="already"):
        validate_rule_name("eval-usage")


def test_write_scaffold_refuses_to_overwrite(tmp_path: Path):
    write_scaffold(NAME, tmp_path)
    with pytest.raises(FileExistsError):
        write_scaffold(NAME, tmp_path)


def test_the_generated_project_passes_its_own_tests(tmp_path: Path):
    """End to end: the starter rule and its test harness work out of the box."""
    project = write_scaffold(NAME, tmp_path)
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(project)],
        capture_output=True,
        text=True,
        env=env,
        cwd=project,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_generated_rule_runs_in_a_real_scan(tmp_path: Path):
    project = write_scaffold(NAME, tmp_path)
    addon = tmp_path / "addons" / "demo"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        '{"name": "demo", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (addon / "models.py").write_text("print('debug')\n")
    code = (
        "import json, sys\n"
        "import odoo_doctor_rules_no_print_statements.rules\n"
        "from odoo_doctor.cli.app import app\n"
        f"app(['scan', {str(tmp_path / 'addons')!r}, '--json'])\n"
    )
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert f'"rule": "{NAME}"' in result.stdout, result.stdout + result.stderr
