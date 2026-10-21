"""Invariants of `fix --upgrade-to`: the report's "mechanical" label and the fixers agree.

Run on copies of the migration corpus cases (`tests/corpus/migration_19`, `migration_fix`);
nothing here edits the corpus itself. `migration_fix/expected_after/` is written by hand,
not produced by the fixers, so a fixer that drifts shows up as a diff.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest
from lxml import etree
from typer.testing import CliRunner

import odoo_doctor.cli.app  # noqa: F401  (registers every rule and fixer)
from odoo_doctor.cli.app import app
from odoo_doctor.core.fixer import default_fixers
from odoo_doctor.core.upgrade import MECHANICAL_RENAMES, MECHANICAL_RULES

CORPUS = Path(__file__).parent / "corpus"
CASES = ["migration_19", "migration_fix"]
runner = CliRunner()


def _copy(case: str, tmp_path: Path) -> Path:
    dest = tmp_path / case
    shutil.copytree(CORPUS / case, dest, ignore=shutil.ignore_patterns("expected*"))
    return dest


def _report(root: Path) -> tuple[dict, list[list[str]]]:
    res = runner.invoke(
        app, ["scan", str(root), "--upgrade-report", "--odoo-version", "19.0", "--json"]
    )
    assert res.exit_code in (0, 1), res.output
    data = json.loads(res.stdout)
    rest = sorted(
        [
            d["rule"],
            Path(d["file_path"]).relative_to(root.resolve()).as_posix(),
            d["confidence"],
        ]
        for m in data["modules"].values()
        for d in m["diagnostics"]
    )
    return data["upgrade_report"]["totals"], rest


def _fix(root: Path):
    res = runner.invoke(app, ["fix", str(root), "--upgrade-to", "19.0", "--fix"])
    assert res.exit_code == 0, res.output
    return res


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("case", CASES)
def test_every_mechanical_finding_disappears_after_fix(case: str, tmp_path: Path):
    root = _copy(case, tmp_path)
    before, _ = _report(root)
    assert before["mechanical"] > 0
    _fix(root)
    after, _ = _report(root)
    assert after["mechanical"] == 0
    assert after["needs_review"] == before["needs_review"]


@pytest.mark.parametrize("case", CASES)
def test_second_run_is_a_noop(case: str, tmp_path: Path):
    root = _copy(case, tmp_path)
    _fix(root)
    first = _snapshot(root)
    _fix(root)
    assert _snapshot(root) == first


@pytest.mark.parametrize("case", CASES)
def test_changed_files_still_parse(case: str, tmp_path: Path):
    root = _copy(case, tmp_path)
    original = _snapshot(root)
    _fix(root)
    changed = [n for n, b in _snapshot(root).items() if original[n] != b]
    assert changed
    for name in changed:
        data = (root / name).read_bytes()
        if name.endswith(".xml"):
            etree.fromstring(data, etree.XMLParser(resolve_entities=False))
        elif name.endswith(".py"):
            ast.parse(data.decode())


def test_fixed_tree_equals_the_hand_written_expectation(tmp_path: Path):
    """Bytes outside the offenders stay as they were (CRLF, BOM, comments, unflagged records)."""
    root = _copy("migration_fix", tmp_path)
    _fix(root)
    expected = CORPUS / "migration_fix" / "expected_after"
    assert _snapshot(root / "mf") == _snapshot(expected / "mf")


def test_files_without_findings_are_byte_identical(tmp_path: Path):
    root = _copy("migration_fix", tmp_path)
    original = _snapshot(root)
    _fix(root)
    after = _snapshot(root)
    for name in ("mf/views/clean.xml", "mf/views/suppressed.xml", "mf/__manifest__.py"):
        assert after[name] == original[name]


def test_remaining_findings_are_the_ones_for_a_person(tmp_path: Path):
    root = _copy("migration_fix", tmp_path)
    _fix(root)
    _, rest = _report(root)
    assert rest == [
        ["chatter-div-removed", "mf/views/forms.xml", "medium"],
        ["view-tree-removed", "mf/models/thing.py", "medium"],
    ]


@pytest.mark.parametrize("case", CASES)
def test_plain_fix_leaves_migration_findings_alone(case: str, tmp_path: Path):
    root = _copy(case, tmp_path)
    original = _snapshot(root)
    res = runner.invoke(app, ["fix", str(root), "--fix"])
    assert res.exit_code == 0, res.output
    assert _snapshot(root) == original


def test_every_mechanical_rule_has_a_migration_fixer():
    for rule in MECHANICAL_RULES | {"removed-core-field-usage"}:
        assert default_fixers.get(rule) is not None, rule
        assert default_fixers.is_migration(rule), rule


@pytest.mark.parametrize(("model", "field"), sorted(MECHANICAL_RENAMES))
def test_every_mechanical_rename_is_fixed(model: str, field: str, tmp_path: Path):
    """The table drives both the label and the fixer; each entry must round-trip."""
    new = MECHANICAL_RENAMES[(model, field)]
    mod = tmp_path / "m"
    (mod / "data").mkdir(parents=True)
    (tmp_path / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        '{"name": "m", "version": "19.0.1.0.0", "depends": ["base"], "data": ["data/d.xml"], "license": "LGPL-3"}\n'
    )
    record = f'<odoo>\n    <record id="r" model="{model}">\n        <field name="{field}" eval="[]"/>\n    </record>\n</odoo>\n'
    (mod / "data" / "d.xml").write_text(record)
    before, _ = _report(tmp_path)
    assert before["mechanical"] == 1, (model, field)
    _fix(tmp_path)
    assert (mod / "data" / "d.xml").read_text() == record.replace(
        f'name="{field}"', f'name="{new}"'
    )
    after, _ = _report(tmp_path)
    assert after["mechanical"] == 0
