# tests/rules/test_xml_rules.py
"""Tests for XML/view rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.duplicate_xml_id import check_duplicate_xml_id
from odoo_doctor.rules.xml.missing_xml_ref import check_missing_xml_ref
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found


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
