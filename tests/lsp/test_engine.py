"""Scanning a project for the language server."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp  # noqa: E402

from odoo_doctor.lsp.actions import find_finding  # noqa: E402
from odoo_doctor.lsp.convert import file_diagnostics  # noqa: E402
from odoo_doctor.lsp.engine import scan_project  # noqa: E402

RULE = "raw-sql-string-interpolation"


def _project(root: Path, toml_extra: str = "") -> Path:
    (root / "odoo-doctor.toml").write_text(
        '[odoo-doctor]\nodoo_version = "17.0"\n\n'
        "[adapters]\nruff = false\npylint_odoo = false\n\n" + toml_extra
    )
    mod = root / "mod"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    (mod / "models" / "m.py").write_text(
        "from odoo import models\n\n"
        "class M(models.Model):\n"
        "    _name = 'mod.m'\n"
        "    _description = 'M'\n\n"
        "    def run(self, name):\n"
        "        self.env.cr.execute(f\"SELECT 1 FROM t WHERE n = '{name}'\")\n"
    )
    return root


def test_scan_groups_findings_by_absolute_file_path(tmp_path: Path):
    root = _project(tmp_path)
    by_file = scan_project(root)
    path = str((root / "mod" / "models" / "m.py").resolve())
    assert RULE in {d.rule for d in by_file[path]}
    assert all(Path(p).is_absolute() for p in by_file)


def test_scan_honours_the_project_config(tmp_path: Path):
    root = _project(tmp_path, toml_extra=f'[ignore]\nrules = ["{RULE}"]\n')
    all_rules = {d.rule for ds in scan_project(root).values() for d in ds}
    assert RULE not in all_rules


def test_a_rescan_sees_the_edited_file(tmp_path: Path):
    root = _project(tmp_path)
    path = root / "mod" / "models" / "m.py"
    assert RULE in {d.rule for d in scan_project(root)[str(path.resolve())]}
    path.write_text(
        "from odoo import models\n\n"
        "class M(models.Model):\n"
        "    _name = 'mod.m'\n"
        "    _description = 'M'\n\n"
        "    def run(self, name):\n"
        "        self.env.cr.execute('SELECT 1 FROM t WHERE n = %s', (name,))\n"
        "        return None\n"
    )
    after = scan_project(root).get(str(path.resolve()), [])
    assert RULE not in {d.rule for d in after}


def test_file_diagnostics_read_the_line_text(tmp_path: Path):
    root = _project(tmp_path)
    path = root / "mod" / "models" / "m.py"
    findings = scan_project(root)[str(path.resolve())]
    diags = file_diagnostics(str(path.resolve()), findings)
    sql = next(d for d in diags if d.code == RULE)
    assert sql.range.start == lsp.Position(line=7, character=8)
    assert sql.range.end.character > sql.range.start.character


def test_file_diagnostics_survive_an_unreadable_file(tmp_path: Path):
    root = _project(tmp_path)
    path = root / "mod" / "models" / "m.py"
    findings = scan_project(root)[str(path.resolve())]
    gone = str((root / "gone.py").resolve())
    from dataclasses import replace

    diags = file_diagnostics(gone, [replace(f, file_path=gone) for f in findings])
    assert diags and all(d.range.start.character == 0 for d in diags)


def test_find_finding_matches_by_rule_and_line(tmp_path: Path):
    root = _project(tmp_path)
    path = root / "mod" / "models" / "m.py"
    findings = scan_project(root)[str(path.resolve())]
    diag = next(
        d for d in file_diagnostics(str(path.resolve()), findings) if d.code == RULE
    )
    found = find_finding(findings, diag)
    assert found is not None and found.rule == RULE and found.line == 8
    other = lsp.Diagnostic(
        range=lsp.Range(lsp.Position(0, 0), lsp.Position(0, 1)),
        message="x",
        code="no-such-rule",
    )
    assert find_finding(findings, other) is None
