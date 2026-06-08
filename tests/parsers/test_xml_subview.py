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
