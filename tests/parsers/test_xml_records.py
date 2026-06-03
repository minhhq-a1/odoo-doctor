# tests/parsers/test_xml_records.py
"""Tests for XML/view parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.xml_records import (
    ViewInfo,
    XmlIdInfo,
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
