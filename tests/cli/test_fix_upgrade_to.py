"""`odoo-doctor fix --upgrade-to`: the opt-in migration fixes."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()

VIEWS = """<odoo>
    <record id="v_list" model="ir.ui.view">
        <field name="name">v.list</field>
        <field name="model">m.thing</field>
        <field name="arch" type="xml">
            <tree><field name="name"/></tree>
        </field>
    </record>
    <record id="v_form" model="ir.ui.view">
        <field name="name">v.form</field>
        <field name="model">m.thing</field>
        <field name="arch" type="xml">
            <form>
                <sheet><field name="name"/></sheet>
                <div class="oe_chatter">
                    <field name="message_ids"/>
                </div>
            </form>
        </field>
    </record>
    <record id="v_custom" model="ir.ui.view">
        <field name="name">v.custom</field>
        <field name="model">m.thing</field>
        <field name="priority">20</field>
        <field name="arch" type="xml">
            <form><div class="oe_chatter"><span>custom</span></div></form>
        </field>
    </record>
    <record id="v_skipped" model="ir.ui.view">
        <field name="name">v.skipped</field>
        <field name="model">m.thing</field>
        <field name="priority">30</field>
        <field name="arch" type="xml">
            <!-- odoo-doctor: disable=view-tree-removed -->
            <tree><field name="name"/></tree>
        </field>
    </record>
</odoo>
"""


def _addon(root: Path, version: str = "17.0.1.0.0") -> Path:
    (root / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    mod = root / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text(
        repr(
            {
                "name": "M",
                "version": version,
                "depends": ["base"],
                "data": ["views/v.xml"],
                "license": "LGPL-3",
            }
        )
    )
    (mod / "views" / "v.xml").write_text(VIEWS)
    return mod


@pytest.fixture
def addon(tmp_path: Path) -> Path:
    return _addon(tmp_path)


def _run(root: Path, *args: str):
    return runner.invoke(app, ["fix", str(root), *args])


def test_fix_without_the_flag_never_touches_migration_findings(tmp_path: Path):
    mod = _addon(tmp_path, "19.0.1.0.0")  # declares 19.0: the rules fire
    before = (mod / "views" / "v.xml").read_text()

    result = _run(tmp_path, "--fix")

    assert result.exit_code == 0 and "Applied 0 fix(es)" in result.stdout
    assert (mod / "views" / "v.xml").read_text() == before


@pytest.mark.parametrize(
    "args",
    [
        ["--upgrade-to", "19.0", "--odoo-version", "19.0", "--fix"],
        ["--upgrade-to", "17.0", "--fix"],
        ["--upgrade-to", "nineteen", "--fix"],
        ["--upgrade-to", "19.0"],
    ],
)
def test_bad_arguments_exit_3(addon: Path, args: list[str]):
    assert _run(addon.parent, *args).exit_code == 3


def test_dry_run_prints_the_diff_and_writes_nothing(addon: Path):
    before = (addon / "views" / "v.xml").read_text()

    result = _run(addon.parent, "--upgrade-to", "19.0", "--fix-dry-run")

    assert result.exit_code == 0
    assert (
        "-            <tree>" in result.stdout
        and "+            <list>" in result.stdout
    )
    assert "would still need review" in result.stdout
    assert (addon / "views" / "v.xml").read_text() == before


def test_apply_fixes_the_mechanical_part_and_lists_the_rest(addon: Path):
    manifest = (addon / "__manifest__.py").read_text()

    result = _run(addon.parent, "--upgrade-to", "19.0", "--fix")

    assert result.exit_code == 0, result.output
    out = (addon / "views" / "v.xml").read_text()
    assert out == (
        VIEWS.replace(
            '<tree><field name="name"/></tree>\n        </field>\n    </record>\n    <record id="v_form"',
            '<list><field name="name"/></list>\n        </field>\n    </record>\n    <record id="v_form"',
        ).replace(
            '<div class="oe_chatter">\n                    <field name="message_ids"/>\n                </div>',
            "<chatter/>",
        )
    )
    assert "<tree>" in out  # the suppressed record
    assert 'class="oe_chatter"><span>' in out  # custom content needs a person
    assert (addon / "__manifest__.py").read_text() == manifest  # version untouched
    assert "need review" in result.stdout and "What is left to do" in result.stdout
    assert "manifest version of m still names an older Odoo" in result.stdout


def test_second_run_changes_nothing(addon: Path):
    _run(addon.parent, "--upgrade-to", "19.0", "--fix")
    after_first = (addon / "views" / "v.xml").read_text()

    result = _run(addon.parent, "--upgrade-to", "19.0", "--fix")

    assert "Applied 0 fix(es)" in result.stdout
    assert (addon / "views" / "v.xml").read_text() == after_first


def test_crlf_file_keeps_its_line_endings(tmp_path: Path):
    mod = _addon(tmp_path)
    (mod / "views" / "v.xml").write_bytes(VIEWS.replace("\n", "\r\n").encode())

    _run(tmp_path, "--upgrade-to", "19.0", "--fix")

    data = (mod / "views" / "v.xml").read_bytes()
    assert (
        b"<list>" in data
        and b"\r\n" in data
        and b"\n" not in data.replace(b"\r\n", b"")
    )
