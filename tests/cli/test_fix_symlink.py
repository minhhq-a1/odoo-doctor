"""`fix --fix` writes only inside the scanned directory, whatever a symlink points at."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()

MANIFEST = (
    "{\n    'name': 'My Addon',\n    'version': '17.0.1.0.0',\n"
    "    'depends': ['base'],\n    'data': [],\n    'installable': True,\n}\n"
)


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="no symlinks")
@pytest.mark.parametrize("flag", ["--fix", "--fix-dry-run"])
def test_fix_does_not_follow_a_symlinked_manifest_out_of_the_repo(
    tmp_path: Path, flag: str
):
    repo = tmp_path / "repo"
    mod = repo / "my_addon"
    mod.mkdir(parents=True)
    (repo / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    (mod / "__init__.py").touch()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manifest.py").write_text(MANIFEST)  # no license: fixable
    try:
        (mod / "__manifest__.py").symlink_to(outside / "manifest.py")
    except OSError:
        pytest.skip("cannot create symlinks")

    result = runner.invoke(app, ["fix", str(repo), flag])
    assert (outside / "manifest.py").read_text() == MANIFEST
    warns = [ln for ln in result.stderr.splitlines() if "__manifest__.py" in ln]
    assert len(warns) == 1 and "outside" in warns[0], result.stderr
