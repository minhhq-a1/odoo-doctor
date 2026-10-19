"""view-attrs-states-removed: Odoo 17+ rejects `attrs` and `states` in view architectures."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.upgrade_safety.view_attrs_states_removed import (
    check_view_attrs_states_removed,
)

FORM = """<odoo>
    <record id="view_a_form" model="ir.ui.view">
        <field name="name">a.form</field>
        <field name="model">x.a</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="act" type="object" states="draft"/>
                </header>
                <field name="note" attrs="{{'invisible': [('state', '=', 'draft')]}}"/>
                <field name="ok" invisible="state == 'draft'"/>
            </form>
        </field>
    </record>
</odoo>
"""


def _diags(tmp_path: Path, xml: str, version: str = "17.0"):
    addon = tmp_path / "mod"
    (addon / "views").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": "mod",
                "version": f"{version}.1.0.0",
                "depends": [],
                "license": "LGPL-3",
                "data": ["views/v.xml"],
            }
        )
    )
    (addon / "__init__.py").write_text("")
    (addon / "views" / "v.xml").write_text(xml)
    ctx = build_project_graph([tmp_path], odoo_version=version).modules["mod"]
    return check_view_attrs_states_removed(ctx)


def test_attrs_and_states_in_a_view_are_flagged_once_per_view(tmp_path: Path):
    diags = _diags(tmp_path, FORM.format())
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "view-attrs-states-removed",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert d.line == 8  # the first offending element
    assert "2 element(s)" in d.message
    assert "invisible" in d.help


def test_xpath_attribute_named_attrs_is_flagged(tmp_path: Path):
    xml = """<odoo><record id="v" model="ir.ui.view">
        <field name="model">x.a</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='x']" position="attributes">
                <attribute name="attrs">{'invisible': [('a', '=', 1)]}</attribute>
            </xpath>
        </field></record></odoo>"""
    assert len(_diags(tmp_path, xml)) == 1


def test_modern_view_is_clean(tmp_path: Path):
    xml = """<odoo><record id="v" model="ir.ui.view">
        <field name="model">x.a</field>
        <field name="arch" type="xml"><form>
            <field name="a" invisible="b" readonly="state != 'draft'"/>
        </form></field></record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_qweb_template_is_not_flagged(tmp_path: Path):
    xml = """<odoo>
        <template id="t"><div attrs="x" states="y"/></template>
        <record id="v" model="ir.ui.view">
            <field name="type">qweb</field>
            <field name="arch" type="xml"><t t-name="w"><div states="y"/></t></field>
        </record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_other_models_are_not_flagged(tmp_path: Path):
    xml = """<odoo><record id="a" model="ir.actions.act_window">
        <field name="arch" attrs="x"/></record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_rule_only_runs_from_odoo_17():
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m
        for m, _ in default_registry.get_rules()
        if m.name == "view-attrs-states-removed"
    )
    assert meta.min_version == "17.0"


def test_empty_attribute_edit_that_removes_states_is_not_flagged(tmp_path: Path):
    xml = """<odoo><record id="v" model="ir.ui.view">
        <field name="model">x.a</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <xpath expr="//button[@name='go']" position="attributes">
                <attribute name="invisible">state != 'confirm'</attribute>
                <attribute name="states"></attribute>
                <attribute name="attrs"/>
            </xpath>
        </field></record></odoo>"""
    assert _diags(tmp_path, xml) == []


KANBAN = """<odoo><record id="v" model="ir.ui.view">
    <field name="model">x.a</field>
    <field name="arch" type="xml"><kanban>
        <field name="state"/>
        {outside}
        <templates>
            <t t-name="card">
                <div t-if="record.state.raw_value == 'draft'" attrs="{{'invisible': []}}">
                    <button name="go" type="object" states="draft"/>
                    <field name="name"/>
                </div>
            </t>
        </templates>
    </kanban></field></record></odoo>"""


def test_kanban_outside_its_templates_is_checked(tmp_path: Path):
    xml = KANBAN.format(outside='<field name="note" attrs="{\'invisible\': []}"/>')
    (d,) = _diags(tmp_path, xml)
    assert d.line == 5
    assert "1 element(s)" in d.message


def test_kanban_templates_are_qweb_and_not_flagged(tmp_path: Path):
    assert _diags(tmp_path, KANBAN.format(outside="")) == []


def test_kanban_button_with_states_outside_templates_is_flagged(tmp_path: Path):
    xml = KANBAN.format(outside='<button name="x" type="object" states="draft"/>')
    assert len(_diags(tmp_path, xml)) == 1


def test_xpath_into_a_kanban_template_is_qweb(tmp_path: Path):
    xml = """<odoo><record id="v" model="ir.ui.view">
        <field name="model">x.a</field>
        <field name="inherit_id" ref="x.kanban"/>
        <field name="arch" type="xml">
            <xpath expr="//t[@t-name='card']" position="inside">
                <div states="draft"/>
            </xpath>
            <xpath expr="//templates" position="inside">
                <t t-name="extra"><div attrs="x"/></t>
            </xpath>
        </field></record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_qweb_branch_in_a_regular_view_is_skipped_but_the_rest_is_checked(
    tmp_path: Path,
):
    xml = """<odoo><record id="v" model="ir.ui.view">
        <field name="model">x.a</field>
        <field name="arch" type="xml"><form>
            <div t-if="x" states="draft"/>
            <field name="a" attrs="{'invisible': []}"/>
        </form></field></record></odoo>"""
    (d,) = _diags(tmp_path, xml)
    assert d.line == 5 and "1 element(s)" in d.message
