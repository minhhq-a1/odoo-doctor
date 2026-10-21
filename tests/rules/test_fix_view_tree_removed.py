"""fix_view_tree_removed: <tree> becomes <list> in the record (or action dict) of a finding."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.upgrade_safety.fixers import fix_view_tree_removed
from odoo_doctor.rules.upgrade_safety.view_tree_removed import check_view_tree_removed

from ._fix import fix_files
from ._module import view


def _fix(tmp_path: Path, files: dict[str, str]):
    return fix_files(tmp_path, files, check_view_tree_removed, fix_view_tree_removed)


def _assert_idempotent(tmp_path: Path, texts: dict[str, str]):
    again = tmp_path / "again"
    again.mkdir()
    diags, texts2, result = _fix(again, texts)
    assert diags == [] and texts2 == texts and result.changed_files == {}


def test_tree_element_and_nested_tree_renamed(tmp_path: Path):
    arch = (
        '<tree editable="bottom" decoration-danger="x">\n'
        '<field name="a"/><field name="lines"><tree><field name="b"/></tree></field>\n'
        "<tree/></tree>"
    )
    diags, texts, result = _fix(tmp_path, {"v.xml": view(arch)})
    assert len(diags) == 1 and result.skipped_count == 0
    assert texts["v.xml"] == view(
        arch.replace("<tree", "<list").replace("</tree>", "</list>")
    )
    _assert_idempotent(tmp_path, texts)


def test_two_trees_on_one_line(tmp_path: Path):
    arch = '<form><tree><field name="a"/></tree><tree><field name="b"/></tree></form>'
    _, texts, _ = _fix(tmp_path, {"v.xml": view(arch)})
    assert "tree" not in texts["v.xml"].split('type="xml">')[1]


def test_xpath_step_renamed_but_predicate_untouched(tmp_path: Path):
    arch = (
        '<data><xpath expr="//tree/field[@name=\'tree\']" position="after">'
        '<field name="x"/></xpath></data>'
    )
    diags, texts, _ = _fix(tmp_path, {"v.xml": view(arch)})
    assert len(diags) == 1
    assert "//list/field[@name='tree']" in texts["v.xml"]


def test_type_field_renamed(tmp_path: Path):
    xml = (
        '<odoo><record id="v" model="ir.ui.view">\n<field name="model">m</field>\n'
        '<field name="type">tree</field>\n'
        '<field name="arch" type="xml"><data/></field></record></odoo>'
    )
    _, texts, _ = _fix(tmp_path, {"v.xml": xml})
    assert '<field name="type">list</field>' in texts["v.xml"]


def test_action_view_mode_text_and_eval(tmp_path: Path):
    xml = (
        '<odoo><record id="a" model="ir.actions.act_window">\n'
        '<field name="res_model">m</field>\n'
        '<field name="view_mode">form, tree ,kanban</field></record>\n'
        '<record id="b" model="ir.actions.act_window">\n'
        '<field name="res_model">m</field>\n'
        "<field name=\"view_mode\" eval=\"{'view_mode': 'tree,form', 'x': 'tree'}\"/></record>\n"
        '<record id="c" model="ir.actions.act_window.view">\n'
        '<field name="view_mode">tree</field></record></odoo>'
    )
    diags, texts, result = _fix(tmp_path, {"a.xml": xml})
    assert len(diags) == 3 and result.skipped_count == 0
    out = texts["a.xml"]
    assert '<field name="view_mode">form, list ,kanban</field>' in out
    assert "{'view_mode': 'list,form', 'x': 'tree'}" in out
    assert '<field name="view_mode">list</field>' in out
    _assert_idempotent(tmp_path, texts)


def test_comment_cdata_and_other_records_untouched(tmp_path: Path):
    xml = (
        "<odoo>\n<!-- <tree> in a comment -->\n"
        '<record id="ok" model="ir.ui.view"><field name="arch" type="xml">'
        "<list/></field></record>\n"
        '<record id="v" model="ir.ui.view"><field name="arch" type="xml">'
        "<tree/></field></record>\n</odoo>"
    )
    _, texts, _ = _fix(tmp_path, {"a.xml": xml})
    assert texts["a.xml"] == xml.replace("<tree/>", "<list/>")


def test_crlf_and_bom_preserved(tmp_path: Path):
    xml = ("\ufeff" + view("<tree>\n<field name='a'/>\n</tree>")).replace("\n", "\r\n")
    diags, texts, _ = _fix(tmp_path, {"v.xml": xml})
    assert len(diags) == 1
    assert texts["v.xml"] == xml.replace("<tree>", "<list>").replace(
        "</tree>", "</list>"
    )


def test_stale_line_returns_none():
    diag = Diagnostic(
        module="m", file_path="v.xml", line=99, column=0, rule="view-tree-removed",
        category="Upgrade Safety", severity="error", tier="P1", source="native",
        confidence="high", title="t", message="m", help="h", odoo_version="19.0",
    )  # fmt: skip
    assert fix_view_tree_removed(diag, view("<list/>")) is None
