# tests/parsers/test_xml_subview.py
"""Subview fields must not be attributed to the parent view's model (A5)."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.parsers.xml_records import parse_views


def _write(tmp_path: Path, xml: str) -> Path:
    f = tmp_path / "v.xml"
    f.write_text(xml)
    return f


def test_nested_field_not_attributed_to_parent(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
<odoo>
  <record id="view_form" model="ir.ui.view">
    <field name="model">my.parent</field>
    <field name="arch" type="xml">
      <form>
        <field name="name"/>
        <field name="line_ids">
          <tree>
            <field name="child_only_field"/>
            <button name="action_in_subview" type="object"/>
          </tree>
        </field>
      </form>
    </field>
  </record>
</odoo>
""",
    )
    views = parse_views(f, module_name="m")
    assert len(views) == 1
    v = views[0]
    # Top-level fields ARE attributed:
    assert "name" in v.field_refs
    assert "line_ids" in v.field_refs
    # Nested subview field/button are NOT attributed to my.parent:
    assert "child_only_field" not in v.field_refs
    assert "action_in_subview" not in v.button_methods


# --- inherited views: xpath into a subview, and locators ---------------------


def _inherited(tmp_path: Path, body: str):
    f = _write(
        tmp_path,
        f"""\
<odoo>
  <record id="view_inherit" model="ir.ui.view">
    <field name="model">my.parent</field>
    <field name="inherit_id" ref="m.view_form"/>
    <field name="arch" type="xml">
      <data>
        {body}
      </data>
    </field>
  </record>
</odoo>
""",
    )
    (view,) = parse_views(f, module_name="m")
    return view


def test_fields_added_through_an_xpath_into_a_subview_are_not_attributed(
    tmp_path: Path,
):
    for expr in (
        "//field[@name='order_line']//list//field[@name='qty']",  # through the x2many
        "//notebook/page[@name='lines']//list/field[@name='name']",  # list is not the root
        "//field[@name='rule_ids']//field[@name='domain']",  # field inside a field
    ):
        view = _inherited(
            tmp_path,
            f"""<xpath expr="{expr}" position="after">
                 <field name="line_only_field"/>
                 <button name="action_line" type="object"/>
               </xpath>""",
        )
        assert "line_only_field" not in view.field_refs, expr
        assert "action_line" not in view.button_methods, expr


def test_fields_added_through_a_view_level_xpath_are_still_attributed(tmp_path: Path):
    for expr in (
        "//field[@name='partner_id']",  # the field step is the last one: same level
        "//group[@name='main']",
        "//sheet/group/field[@name='partner_id']",
        "//list/field[@name='name']",  # list as the first step: the root of a list view
    ):
        view = _inherited(
            tmp_path,
            f"""<xpath expr="{expr}" position="after">
                 <field name="own_field"/>
                 <button name="action_own" type="object"/>
               </xpath>""",
        )
        assert "own_field" in view.field_refs, expr
        assert "action_own" in view.button_methods, expr


def test_a_field_locator_is_not_a_reference(tmp_path: Path):
    # `<field name="duration" position="after">` only locates a node of the parent view,
    # which may sit in one of its subviews; Odoo checks locators when the view loads.
    view = _inherited(
        tmp_path,
        """<field name="located_elsewhere" position="after">
             <field name="new_field"/>
           </field>
           <field name="plain_ref"/>""",
    )
    assert "located_elsewhere" not in view.field_refs
    assert "plain_ref" in view.field_refs


def test_refs_inserted_by_an_xpath_remember_the_field_it_targets(tmp_path: Path):
    view = _inherited(
        tmp_path,
        """<xpath expr="//field[@name='pattern']" position="after">
             <field name="a"/>
             <group><button name="act" type="object"/></group>
           </xpath>
           <xpath expr="//group[@name='main']" position="inside"><field name="b"/></xpath>
           <field name="c"/>""",
    )
    assert view.field_ref_anchors == {"a": "pattern", "b": None, "c": None}
    assert view.button_method_anchors == {"act": "pattern"}


def test_a_name_seen_with_two_different_anchors_is_not_anchored(tmp_path: Path):
    view = _inherited(
        tmp_path,
        """<xpath expr="//field[@name='p']" position="after"><field name="a"/></xpath>
           <xpath expr="//field[@name='q']" position="after"><field name="a"/></xpath>
           <xpath expr="//field[@name='p']" position="after"><field name="d"/></xpath>
           <field name="d"/>""",
    )
    assert view.field_ref_anchors["a"] is None  # two targets: attribute it to the model
    assert view.field_ref_anchors["d"] is None  # also seen outside any xpath


def test_a_groupby_belongs_to_the_group_model_not_the_views(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
<odoo>
  <record id="view_list" model="ir.ui.view">
    <field name="model">my.line</field>
    <field name="arch" type="xml">
      <list>
        <field name="name"/>
        <groupby name="move_id">
          <field name="move_only_field"/>
          <button name="action_post" type="object"/>
        </groupby>
      </list>
    </field>
  </record>
</odoo>
""",
    )
    (view,) = parse_views(f, module_name="m")
    assert view.field_refs == ["name"]
    assert view.button_methods == []
