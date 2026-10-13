"""view-tree-removed: Odoo 18 renamed the tree view type to list."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.view_tree_removed import check_view_tree_removed

from ._module import module_ctx, view


def _diags(tmp_path: Path, files: dict[str, str], version="19.0"):
    return check_view_tree_removed(module_ctx(tmp_path, files, version))


def test_tree_root_is_flagged(tmp_path: Path):
    diags = _diags(
        tmp_path, {"v.xml": view('<tree><field name="name"/></tree>', "v_tree")}
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence, d.severity) == (
        "view-tree-removed",
        "P1",
        "Upgrade Safety",
        "high",
        "error",
    )
    assert "v_tree" in d.title and "<list>" in d.help
    assert d.line == 5


def test_nested_tree_and_type_field_count_once_per_view(tmp_path: Path):
    xml = view(
        '<form><field name="line_ids"><tree><field name="a"/></tree></field></form>',
        extra='<field name="type">tree</field>\n',
    )
    diags = _diags(tmp_path, {"v.xml": xml})
    assert len(diags) == 1
    assert "type tree" in diags[0].message


def test_xpath_step_named_tree(tmp_path: Path):
    xml = view(
        "<xpath expr=\"//field[@name='x']/tree/field[@name='y']\" position=\"after\"/>"
    )
    assert len(_diags(tmp_path, {"v.xml": xml})) == 1


@pytest.mark.parametrize(
    "expr", ["//field[@name='tree']", "//list/field", "//field[@name='streets']"]
)
def test_xpath_without_a_tree_step_is_fine(tmp_path: Path, expr: str):
    assert (
        _diags(tmp_path, {"v.xml": view(f'<xpath expr="{expr}" position="after"/>')})
        == []
    )


def test_list_view_is_clean(tmp_path: Path):
    assert _diags(tmp_path, {"v.xml": view('<list><field name="name"/></list>')}) == []


ACTION = """<odoo><record id="act" model="ir.actions.act_window">
<field name="name">A</field>
<field name="res_model">x.model</field>
<field name="view_mode">{mode}</field>
</record></odoo>"""


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("tree,form", 1),
        ("form,tree", 1),
        ("tree", 1),
        ("list,form", 0),
        ("form,kanban", 0),
    ],
)
def test_action_view_mode(tmp_path: Path, mode: str, expected: int):
    assert len(_diags(tmp_path, {"a.xml": ACTION.format(mode=mode)})) == expected


def test_action_view_ids_given_through_eval(tmp_path: Path):
    xml = """<odoo><record id="act" model="ir.actions.act_window">
<field name="res_model">x.model</field>
<field name="view_ids" eval="[(5, 0, 0), (0, 0, {'view_mode': 'tree', 'view_id': ref('v')})]"/>
</record></odoo>"""
    assert len(_diags(tmp_path, {"a.xml": xml})) == 1


def test_act_window_view_record(tmp_path: Path):
    xml = """<odoo><record id="act_v" model="ir.actions.act_window.view">
<field name="view_mode">tree</field></record></odoo>"""
    assert len(_diags(tmp_path, {"a.xml": xml})) == 1


def test_python_action_dicts(tmp_path: Path):
    py = (
        "def go(self):\n"
        "    return {'type': 'ir.actions.act_window', 'res_model': 'x', 'view_mode': 'tree,form'}\n"
        "def pick(self):\n"
        "    return {'res_model': 'x', 'views': [(False, 'tree'), (False, 'form')]}\n"
        "def other(self):\n"
        "    return {'view_mode': 'tree'}\n"
        "def ok(self):\n"
        "    return {'res_model': 'x', 'view_mode': 'list,form', 'views': [(False, 'list')]}\n"
    )
    diags = _diags(tmp_path, {"models/m.py": py})
    assert [(d.line, d.confidence) for d in diags] == [
        (2, "high"),
        (4, "high"),
        (6, "medium"),
    ]


def test_not_run_before_odoo_18(tmp_path: Path):
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m for m, _ in default_registry.get_rules() if m.name == "view-tree-removed"
    )
    assert meta.min_version == "18.0"


def test_qweb_templates_and_unloaded_files_are_skipped(tmp_path: Path):
    qweb = view("<tree/>", extra='<field name="type">qweb</field>\n')
    files = {"v.xml": qweb, "unloaded.xml": view("<tree/>")}
    assert check_view_tree_removed(module_ctx(tmp_path, files, data=["v.xml"])) == []


def test_python_in_tests_and_migrations_is_skipped(tmp_path: Path):
    py = "def go(self):\n    return {'res_model': 'x', 'view_mode': 'tree'}\n"
    assert _diags(tmp_path, {"tests/t.py": py, "migrations/18.0.1/p.py": py}) == []
