"""manifest-data-order-risk: high only when an earlier file loads a group a later one creates."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.manifest.data_order_risk import (
    risky_security_files,
    safe_placement,
)

GROUP = '<odoo><record id="{id}" model="res.groups"/></odoo>'
MENU = '<odoo><menuitem id="menu_x" name="X" groups="{groups}"/></odoo>'


def _module(tmp_path: Path, files: dict[str, str]) -> Path:
    mod = tmp_path / "m"
    for rel, text in files.items():
        (mod / rel).parent.mkdir(parents=True, exist_ok=True)
        (mod / rel).write_text(text)
    return mod


def _risk(tmp_path, files, data):
    return risky_security_files(_module(tmp_path, files), "m", data)


def test_menu_group_created_by_later_file_is_high(tmp_path):
    files = {
        "views/menu.xml": MENU.format(groups="m.group_x"),
        "security/groups.xml": GROUP.format(id="group_x"),
    }
    assert _risk(tmp_path, files, list(files)) == (["security/groups.xml"], [])


def test_unqualified_and_qualified_references_both_match(tmp_path):
    for i, groups in enumerate(("group_x", "m.group_x", "!m.group_x,base.group_user")):
        files = {
            "views/menu.xml": MENU.format(groups=groups),
            "security/groups.xml": GROUP.format(id="group_x"),
        }
        high, _ = _risk(tmp_path / str(i), files, list(files))
        assert high == ["security/groups.xml"], groups


def test_reference_to_another_group_is_medium(tmp_path):
    files = {
        "views/menu.xml": MENU.format(groups="base.group_user"),
        "security/groups.xml": GROUP.format(id="group_y"),
    }
    assert _risk(tmp_path, files, list(files)) == ([], ["security/groups.xml"])


def test_view_arch_reference_only_warns_so_medium(tmp_path):
    files = {
        "views/v.xml": '<odoo><record id="v" model="ir.ui.view"><field name="arch" type="xml">'
        '<form><field name="a" groups="m.group_x"/></form></field></record></odoo>',
        "security/groups.xml": GROUP.format(id="group_x"),
    }
    assert _risk(tmp_path, files, list(files)) == ([], ["security/groups.xml"])


def test_load_time_constructs_that_raise_are_high(tmp_path):
    for i, view in enumerate(
        (
            '<odoo><record id="a" model="ir.ui.view"><field name="groups_id" eval="[(4, ref(\'group_x\'))]"/></record></odoo>',
            '<odoo><record id="a" model="ir.ui.view"><field name="group_ids" ref="m.group_x"/></record></odoo>',
            '<odoo><template id="t" groups="m.group_x"><p/></template></odoo>',
        )
    ):
        files = {"views/v.xml": view, "security/groups.xml": GROUP.format(id="group_x")}
        assert _risk(tmp_path / str(i), files, list(files))[0], view


def test_csv_is_medium(tmp_path):
    files = {
        "views/v.xml": MENU.format(groups="base.group_user"),
        "security/ir.model.access.csv": "id,name\n",
    }
    assert _risk(tmp_path, files, list(files)) == ([], ["security/ir.model.access.csv"])


def test_malformed_xml_never_raises(tmp_path):
    files = {"views/v.xml": "<odoo><menuitem", "security/groups.xml": "<odoo><record"}
    assert _risk(tmp_path, files, list(files)) == ([], ["security/groups.xml"])


def test_missing_file_is_ignored(tmp_path):
    mod = _module(tmp_path, {})
    data = ["views/v.xml", "security/groups.xml"]
    assert risky_security_files(mod, "m", data) == ([], ["security/groups.xml"])


def test_update_of_an_existing_group_is_not_a_definition(tmp_path):
    files = {
        "security/base_groups.xml": GROUP.format(id="group_x"),
        "views/menu.xml": MENU.format(groups="m.group_x"),
        "security/override.xml": GROUP.format(id="group_x"),
    }
    assert _risk(tmp_path, files, list(files)) == ([], ["security/override.xml"])


def test_declaring_someone_elses_group_is_an_update(tmp_path):
    files = {
        "views/menu.xml": MENU.format(groups="base.group_user"),
        "security/override.xml": GROUP.format(id="base.group_user"),
    }
    assert _risk(tmp_path, files, list(files)) == ([], ["security/override.xml"])


CATEGORY = '<odoo><record id="cat_x" model="ir.module.category"/></odoo>'
CATEGORISED = (
    '<odoo><record id="group_x" model="res.groups">'
    '<field name="category_id" ref="cat_x"/></record></odoo>'
)


def test_safe_placement_goes_in_front_of_the_consumer_after_its_category(tmp_path):
    files = {
        "data/category.xml": CATEGORY,
        "views/menu.xml": MENU.format(groups="m.group_x"),
        "security/groups.xml": CATEGORISED,
    }
    mod = _module(tmp_path, files)
    data = list(files)
    assert risky_security_files(mod, "m", data)[0] == ["security/groups.xml"]
    assert safe_placement(mod, "m", data) == {"security/groups.xml": 1}


def test_safe_placement_declines_when_a_dependency_sits_in_between(tmp_path):
    files = {
        "views/menu.xml": MENU.format(groups="m.group_x"),
        "data/category.xml": CATEGORY,
        "security/groups.xml": CATEGORISED,
    }
    mod = _module(tmp_path, files)
    data = list(files)
    assert risky_security_files(mod, "m", data)[0] == ["security/groups.xml"]
    assert safe_placement(mod, "m", data) is None
