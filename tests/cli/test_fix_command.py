"""End-to-end tests for `odoo-doctor fix`."""

from __future__ import annotations

import ast
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


@pytest.fixture
def local_tmp() -> Iterator[Path]:
    import uuid

    # Use a directory inside the workspace to allow sandbox writes
    ws_tmp = Path(__file__).parent.parent.parent / ".tmp" / str(uuid.uuid4())
    ws_tmp.mkdir(parents=True, exist_ok=True)
    yield ws_tmp
    shutil.rmtree(ws_tmp, ignore_errors=True)


def _write_addon(root: Path) -> Path:
    (root / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    mod = root / "my_addon"
    (mod / "security").mkdir(parents=True)
    (mod / "views").mkdir(parents=True)
    (mod / "__init__.py").touch()
    # Missing 'license' and data ordering wrong: the menu needs a group that the
    # later security file creates (a load-time error in Odoo).
    (mod / "__manifest__.py").write_text(
        "{\n    'name': 'My Addon',\n    'version': '17.0.1.0.0',\n"
        "    'depends': ['base'],\n    'data': [\n        'views/v.xml',\n"
        "        'security/groups.xml',\n        'security/ir.model.access.csv',\n"
        "    ],\n    'installable': True,\n}\n"
    )
    (mod / "views" / "v.xml").write_text(
        '<odoo><menuitem id="menu_x" name="X" groups="my_addon.group_x"/></odoo>'
    )
    (mod / "security" / "groups.xml").write_text(
        '<odoo><record id="group_x" model="res.groups"/></odoo>'
    )
    (mod / "security" / "ir.model.access.csv").write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
    )
    return mod


def test_fix_dry_run_emits_diff_and_does_not_write(local_tmp: Path):
    mod = _write_addon(local_tmp)
    before = (mod / "__manifest__.py").read_text()

    result = runner.invoke(app, ["fix", str(local_tmp), "--fix-dry-run"])
    assert result.exit_code == 0
    assert "--- a/" in result.stdout and "+++ b/" in result.stdout
    # Dry run must not modify the file.
    assert (mod / "__manifest__.py").read_text() == before


def test_fix_applies_changes(local_tmp: Path):
    mod = _write_addon(local_tmp)
    result = runner.invoke(app, ["fix", str(local_tmp), "--fix"])
    assert result.exit_code == 0

    data = ast.literal_eval((mod / "__manifest__.py").read_text())
    assert data["license"] == "LGPL-3"
    assert data["data"].index("security/groups.xml") < data["data"].index("views/v.xml")
    # the advisory (medium) csv keeps its place
    assert data["data"][-1] == "security/ir.model.access.csv"


def test_fix_is_idempotent(local_tmp: Path):
    mod = _write_addon(local_tmp)
    runner.invoke(app, ["fix", str(local_tmp), "--fix"])
    after_first = (mod / "__manifest__.py").read_text()
    runner.invoke(app, ["fix", str(local_tmp), "--fix"])
    after_second = (mod / "__manifest__.py").read_text()
    assert after_first == after_second


def test_fix_requires_a_mode_flag(local_tmp: Path):
    _write_addon(local_tmp)
    result = runner.invoke(app, ["fix", str(local_tmp)])
    assert result.exit_code == 3
    assert "--fix" in result.stdout or "--fix" in str(result.output)
