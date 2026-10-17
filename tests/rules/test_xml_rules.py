# tests/rules/test_xml_rules.py
"""Tests for XML/view rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found
from odoo_doctor.rules.xml.duplicate_xml_id import check_duplicate_xml_id
from odoo_doctor.rules.xml.missing_xml_ref import check_missing_xml_ref
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model


def test_duplicate_xml_id_catches_bad_addon(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_duplicate_xml_id(ctx)
    assert len(diags) >= 1
    assert all(d.rule == "duplicate-xml-id" for d in diags)


def test_duplicate_xml_id_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_duplicate_xml_id(ctx)
    assert diags == []


def _dups(tmp_path: Path, files: dict[str, str], name: str = "dup_mod"):
    """Scan a one-addon repo whose data files are *files* (path -> <odoo> body)."""
    mod = tmp_path / name
    for rel, body in files.items():
        (mod / rel).parent.mkdir(parents=True, exist_ok=True)
        (mod / rel).write_text(f"<odoo>{body}</odoo>")
    (mod / "__manifest__.py").write_text(
        f"{{'name': 'n', 'depends': ['base'], 'license': 'LGPL-3', 'data': {list(files)!r}}}"
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    return check_duplicate_xml_id(graph.modules[name])


_CAT = '<record id="c" model="res.partner.category">{}</record>'


def test_duplicate_xml_id_patch_is_not_reported(tmp_path: Path):
    diags = _dups(
        tmp_path,
        {
            "a.xml": _CAT.format('<field name="name">A</field>'),
            "b.xml": _CAT.format('<field name="color">3</field>'),
        },
    )
    assert diags == []


def test_duplicate_xml_id_menuitem_then_record_patch(tmp_path: Path):
    menu = '<menuitem id="m" name="M"/>'
    patch = '<record id="m" model="ir.ui.menu"><field name="{}">{}</field></record>'
    assert _dups(tmp_path, {"a.xml": menu, "b.xml": patch.format("sequence", 5)}) == []


def test_duplicate_xml_id_menuitem_always_sets_its_name(tmp_path: Path):
    menu = '<menuitem id="m" name="M"/>'
    patch = '<record id="m" model="ir.ui.menu"><field name="name">N</field></record>'
    diags = _dups(tmp_path, {"a.xml": menu, "b.xml": patch})
    assert [d.confidence for d in diags] == ["medium"]
    assert "name" in diags[0].message


def test_duplicate_xml_id_same_field_again_is_medium(tmp_path: Path):
    diags = _dups(
        tmp_path,
        {
            "a.xml": _CAT.format('<field name="name">A</field>'),
            "b.xml": _CAT.format('<field name="name@fr">B</field>'),
        },
    )
    assert [(d.confidence, d.file_path.endswith("b.xml")) for d in diags] == [
        ("medium", True)
    ]


def test_duplicate_xml_id_overlap_counts_every_earlier_declaration(tmp_path: Path):
    diags = _dups(
        tmp_path,
        {
            "a.xml": _CAT.format('<field name="name">A</field>'),
            "b.xml": _CAT.format('<field name="color">1</field>'),
            "c.xml": _CAT.format('<field name="color">2</field>'),
        },
    )
    assert [(d.confidence, Path(d.file_path).name) for d in diags] == [
        ("medium", "c.xml")
    ]


def test_duplicate_xml_id_other_model_is_high(tmp_path: Path):
    diags = _dups(
        tmp_path,
        {
            "a.xml": _CAT.format('<field name="name">A</field>'),
            "b.xml": '<record id="c" model="res.partner.title"><field name="name">A</field></record>',
        },
    )
    assert [d.confidence for d in diags] == ["high"]
    assert "res.partner.title" in diags[0].message


def test_duplicate_xml_id_menuitem_vs_view_record_is_high(tmp_path: Path):
    diags = _dups(
        tmp_path,
        {
            "a.xml": '<menuitem id="x" name="X"/>',
            "b.xml": '<record id="x" model="ir.ui.view"><field name="name">X</field></record>',
        },
    )
    assert [d.confidence for d in diags] == ["high"]


def test_duplicate_xml_id_theme_template_and_record_share_a_model(tmp_path: Path):
    files = {
        "a.xml": '<template id="t"><div/></template>',
        "b.xml": '<record id="t" model="theme.ir.ui.view"><field name="active" eval="True"/></record>',
    }
    assert _dups(tmp_path, files, name="theme_dup") == []


def test_duplicate_xml_id_unknown_tag_keeps_high(tmp_path: Path):
    asset = "<asset id='a'><bundle>b</bundle><path>p</path></asset>"
    diags = _dups(tmp_path, {"a.xml": asset, "b.xml": asset})
    assert [d.confidence for d in diags] == ["high"]


def test_view_field_not_in_model_unknown_model(tmp_path: Path):
    """Views referencing completely unknown models -> UNKNOWN -> no false positive."""
    mod = tmp_path / "unknown_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Unknown", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}'
    )
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="view_unknown_form" model="ir.ui.view">
    <field name="model">external.unknown</field>
    <field name="arch" type="xml">
      <form>
        <field name="x_name"/>
        <button name="action_x" type="object"/>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["unknown_mod"]
    assert check_view_field_not_in_model(ctx) == []
    assert check_button_method_not_found(ctx) == []


def test_button_method_found_in_model(tmp_path: Path):
    """Button referencing a method that exists in the module -> no error."""
    mod = tmp_path / "good_btn"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Good Btn", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}'
    )
    models_dir = mod / "models"
    models_dir.mkdir()
    (models_dir / "m.py").write_text(
        dedent("""\
        from odoo import models

        class GoodModel(models.Model):
            _name = "good.model"

            def action_do_it(self):
                return True
    """)
    )
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="view_good_form" model="ir.ui.view">
    <field name="model">good.model</field>
    <field name="arch" type="xml">
      <form>
        <button name="action_do_it" type="object"/>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["good_btn"]
    diags = check_button_method_not_found(ctx)
    assert diags == []


def test_missing_xml_ref_reports_local_missing_ref(tmp_path: Path):
    """A ref to the current module is provably missing after local XML parsing."""
    mod = tmp_path / "bad_ref"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Bad Ref", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}'
    )
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="action_x" model="ir.actions.act_window">
    <field name="view_id" ref="missing_view"/>
  </record>
</odoo>
""")

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["bad_ref"]
    diags = check_missing_xml_ref(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "missing-xml-ref"


def test_missing_xml_ref_reports_local_missing_inherit_id(tmp_path: Path):
    """A view inheriting a missing current-module view should be reported."""
    mod = tmp_path / "bad_inherit"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Bad Inherit", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}'
    )
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="view_child" model="ir.ui.view">
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="missing_parent"/>
    <field name="arch" type="xml"><form/></field>
  </record>
</odoo>
""")

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["bad_inherit"]
    diags = check_missing_xml_ref(ctx)
    assert len(diags) == 1
    assert diags[0].title.startswith("Unresolved inherit_id")


def test_missing_xml_ref_eval(tmp_path: Path):
    mod = tmp_path / "bad_eval_ref"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Bad Eval Ref", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}'
    )
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="group_x" model="res.groups">
    <field name="implied_ids" eval="[(4, ref('missing_local')), (4, ref('sale.group_sale_manager'))]"/>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["bad_eval_ref"]
    diags = check_missing_xml_ref(ctx)
    # missing_local is a local missing ref -> should be flagged
    # sale.group_sale_manager is external unknown -> should NOT be flagged
    assert len(diags) == 1
    assert "missing_local" in diags[0].message
    assert "sale.group_sale_manager" not in diags[0].message


def test_missing_xml_ref_checks_all_record_definitions(tmp_path):
    mod = tmp_path / "dup_ref"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name":"Dup","depends":[],"data":["views/v.xml"],"license":"LGPL-3"}'
    )
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="r" model="ir.actions.act_window">
    <field name="view_id" ref="exists_locally"/>
  </record>
  <record id="exists_locally" model="ir.ui.view"><field name="model">res.partner</field></record>
  <record id="r" model="ir.actions.act_window">
    <field name="view_id" ref="missing_second"/>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["dup_ref"]
    diags = check_missing_xml_ref(ctx)
    assert any("missing_second" in d.message for d in diags)


def test_view_field_line_points_at_field(tmp_path):
    mod = tmp_path / "lined"
    (mod / "models").mkdir(parents=True)
    (mod / "views").mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name":"Lined","depends":[],"data":["views/v.xml"],"license":"LGPL-3"}'
    )
    (mod / "models" / "m.py").write_text(
        "from odoo import models\nclass M(models.Model):\n    _name='lined.m'\n"
    )
    # model defines no 'ghost' field -> NOT_FOUND (repo model is complete)
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="v" model="ir.ui.view">
    <field name="model">lined.m</field>
    <field name="arch" type="xml">
      <form>
        <field name="ghost"/>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["lined"]
    diags = check_view_field_not_in_model(ctx)
    assert len(diags) == 1
    assert diags[0].line == 6  # the <field name="ghost"/> line, not 2 (the <record>)
