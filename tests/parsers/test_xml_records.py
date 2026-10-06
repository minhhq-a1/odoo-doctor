# tests/parsers/test_xml_records.py
"""Tests for XML/view parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.xml_records import (
    parse_views,
    parse_xml_records,
)


def test_parse_xml_records(sample_addon: Path):
    xml_file = sample_addon / "views" / "sale_custom_views.xml"
    records = parse_xml_records(xml_file, module_name="sample_addon")
    ids = {r.xml_id for r in records}
    assert "sample_addon.view_sale_order_custom_form" in ids
    assert "sample_addon.action_custom_wizard" in ids
    assert "sample_addon.menu_custom_wizard" in ids


def test_parse_views(sample_addon: Path):
    xml_file = sample_addon / "views" / "sale_custom_views.xml"
    views = parse_views(xml_file, module_name="sample_addon")
    assert len(views) == 1
    v = views[0]
    assert v.model == "sale.order"
    assert v.inherit_id == "sale.view_order_form"
    assert "custom_note" in v.field_refs


def test_parse_view_with_button(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <record id="view_form" model="ir.ui.view">
                <field name="model">sale.order</field>
                <field name="arch" type="xml">
                    <form>
                        <field name="partner_id"/>
                        <button name="action_confirm" type="object" string="Confirm"/>
                    </form>
                </field>
            </record>
        </odoo>
    """)
    f = tmp_path / "views.xml"
    f.write_text(xml)
    views = parse_views(f, module_name="test_mod")
    assert "partner_id" in views[0].field_refs
    assert "action_confirm" in views[0].button_methods


def test_parse_empty_xml(tmp_path: Path):
    f = tmp_path / "empty.xml"
    f.write_text('<?xml version="1.0"?><odoo></odoo>')
    assert parse_xml_records(f, module_name="m") == []
    assert parse_views(f, module_name="m") == []


def test_ref_extraction(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <record id="rec1" model="ir.actions.act_window">
                <field name="res_model">res.partner</field>
            </record>
        </odoo>
    """)
    f = tmp_path / "data.xml"
    f.write_text(xml)
    records = parse_xml_records(f, module_name="mymod")
    assert records[0].xml_id == "mymod.rec1"
    assert records[0].model == "ir.actions.act_window"


def test_eval_ref_extraction(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <record id="rec1" model="res.groups">
                <field name="implied_ids" eval="[(4, ref('sale.group_sale_manager')), (4, ref('missing_local')), (4, ref('sale.view.order.form'))]"/>
            </record>
        </odoo>
    """)
    f = tmp_path / "data.xml"
    f.write_text(xml)
    records = parse_xml_records(f, module_name="mymod")
    assert len(records) == 1
    assert "sale.group_sale_manager" in records[0].refs
    assert "missing_local" in records[0].refs
    assert "sale.view.order.form" in records[0].refs


# --- only data-level elements define xml ids ---------------------------------


def _ids(tmp_path: Path, xml: str) -> list[str]:
    f = tmp_path / "d.xml"
    f.write_text(xml)
    return [r.xml_id for r in parse_xml_records(f, module_name="m")]


def test_html_ids_inside_templates_and_arch_are_not_xml_ids(tmp_path: Path):
    ids = _ids(
        tmp_path,
        """<odoo>
  <template id="tmpl">
    <div id="html_div"><span id="html_span">x</span></div>
  </template>
  <record id="view" model="ir.ui.view">
    <field name="arch" type="xml">
      <form><setting id="a_setting"/><data><div id="in_arch_data"/></data></form>
    </field>
  </record>
</odoo>""",
    )
    assert ids == ["m.tmpl", "m.view"]


def test_every_kind_of_data_level_element_still_defines_an_id(tmp_path: Path):
    ids = _ids(
        tmp_path,
        """<odoo>
  <record id="rec" model="res.partner"/>
  <menuitem id="top_menu" name="Top">
    <menuitem id="child_menu" name="Child"/>
  </menuitem>
  <act_window id="act" name="A" res_model="res.partner"/>
  <data noupdate="1">
    <record id="in_data" model="res.partner"/>
    <template id="in_data_tmpl"><div id="html"/></template>
  </data>
</odoo>""",
    )
    assert ids == [
        "m.rec",
        "m.top_menu",
        "m.child_menu",
        "m.act",
        "m.in_data",
        "m.in_data_tmpl",
    ]


def test_a_delete_does_not_define_an_id(tmp_path: Path):
    ids = _ids(
        tmp_path,
        """<odoo>
  <delete model="res.partner" id="old_partner"/>
  <record id="old_partner" model="res.partner"/>
</odoo>""",
    )
    assert ids == ["m.old_partner"]
