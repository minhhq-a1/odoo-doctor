"""fix_removed_core_field_usage: only the pure renames of MECHANICAL_RENAMES are fixed."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.fixer import FixerRegistry, compute_fixes
from odoo_doctor.core.upgrade import MECHANICAL_RENAMES, is_mechanical
from odoo_doctor.rules.upgrade_safety.fixers import fix_removed_core_field_usage
from odoo_doctor.rules.upgrade_safety.removed_core_field_usage import (
    _REMOVED_FIELDS,
    check_removed_core_field_usage,
)

from ._module import module_ctx, view


def _fix(tmp_path: Path, files: dict[str, str]):
    ctx = module_ctx(tmp_path, files)
    diags = check_removed_core_field_usage(ctx)
    registry = FixerRegistry()
    registry.register(
        "removed-core-field-usage",
        fix_removed_core_field_usage,
        migration=True,
        applies=is_mechanical,
    )
    result, _ = compute_fixes(
        diags, {"removed-core-field-usage"}, registry, include_migration=True
    )
    addon = tmp_path / "mod"
    texts = {n: (addon / n).read_text(newline="") for n in files}
    for path, new in result.changed_files.items():
        texts[Path(path).relative_to(addon).as_posix()] = new
    return diags, texts, result


def test_field_name_renamed_in_a_data_record(tmp_path: Path):
    xml = (
        '<odoo><record id="u" model="res.users">\n'
        '  <field name="name">x</field>\n'
        "  <field name='groups_id' eval=\"[(4, ref('base.group_user'))]\"/>\n"
        '</record>\n<record id="g" model="res.groups">\n'
        '  <field name="users"\n        eval="[(4, ref(\'base.user_admin\'))]"/>\n</record></odoo>'
    )
    diags, texts, result = _fix(tmp_path, {"d.xml": xml})
    assert len(diags) == 2 and result.skipped_count == 0
    assert texts["d.xml"] == xml.replace("'groups_id'", "'group_ids'").replace(
        '"users"', '"user_ids"'
    )


def test_arch_field_anchor_and_xpath_of_a_res_users_view(tmp_path: Path):
    xml = view(
        '<data><field name="groups_id" position="after"><field name="x"/></field>'
        '<xpath expr="//field[@name=\'groups_id\']" position="replace"/></data>',
        model="res.users",
    )
    diags, texts, result = _fix(tmp_path, {"v.xml": xml})
    assert len(diags) == 2 and result.skipped_count == 0
    assert texts["v.xml"] == xml.replace("groups_id", "group_ids")


def test_entity_quotes_in_the_xpath(tmp_path: Path):
    xml = view(
        '<data><xpath expr="//field[@name=&apos;groups_id&apos;]" position="replace"/></data>',
        model="res.users",
    )
    _, texts, _ = _fix(tmp_path, {"v.xml": xml})
    assert "&apos;group_ids&apos;" in texts["v.xml"]


def test_a_rename_that_changes_meaning_is_not_fixed(tmp_path: Path):
    xml = (
        '<odoo><record id="g" model="res.groups">\n<field name="category_id" ref="base.x"/>\n'
        "</record></odoo>"
    )
    diags, texts, result = _fix(tmp_path, {"d.xml": xml})
    assert len(diags) == 1 and not is_mechanical(diags[0])
    assert texts["d.xml"] == xml and result.changed_files == {}


def test_python_reference_is_medium_and_not_fixed(tmp_path: Path):
    py = "def f(user):\n    return user.groups_id\n"
    diags, texts, _ = _fix(tmp_path, {"m.py": py})
    assert [d.confidence for d in diags] == ["medium"]
    assert texts["m.py"] == py


def test_wrong_line_returns_none(tmp_path: Path):
    xml = '<odoo><record id="u" model="res.users">\n<field name="groups_id"/>\n</record></odoo>'
    diags, _, _ = _fix(tmp_path, {"d.xml": xml})
    moved = diags[0].__class__(**{**diags[0].__dict__, "line": 9})
    assert fix_removed_core_field_usage(moved, xml) is None


def test_the_table_matches_the_rules_own_table():
    for (model, field), new in MECHANICAL_RENAMES.items():
        assert _REMOVED_FIELDS[model][field][1] == new
