# tests/rules/test_confidence_regression.py
"""Part A acceptance: partial stubs never produce high-confidence absence findings;
repo-defined models still do. End-to-end through build_project_graph + real rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found


def _manifest(data_files: list[str]) -> str:
    files = ", ".join(f'"{f}"' for f in data_files)
    return '{"name": "M", "depends": [], "data": [%s], "license": "LGPL-3"}' % files


def test_core_fields_on_partial_stub_produce_no_findings(tmp_path: Path):
    mod = tmp_path / "core_view"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="view_sale_form" model="ir.ui.view">
    <field name="model">sale.order</field>
    <field name="arch" type="xml">
      <form>
        <field name="payment_term_id"/>
        <field name="note"/>
        <field name="client_order_ref"/>
        <field name="id"/>
        <field name="create_uid"/>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["core_view"]
    assert check_view_field_not_in_model(ctx) == []


def test_repo_model_missing_field_is_flagged(tmp_path: Path):
    mod = tmp_path / "own_model"
    (mod / "models").mkdir(parents=True)
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "models" / "m.py").write_text(dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            foo = fields.Char()
    """))
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="view_my_form" model="ir.ui.view">
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <form><field name="foo"/><field name="does_not_exist"/></form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["own_model"]
    diags = check_view_field_not_in_model(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "view-field-not-in-model"
    assert "does_not_exist" in diags[0].message
    assert diags[0].confidence == "high"


def test_inherited_method_resolves_via_extended_methods(tmp_path: Path):
    mod = tmp_path / "ext_method"
    (mod / "models").mkdir(parents=True)
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "models" / "m.py").write_text(dedent("""\
        from odoo import models

        class SaleOrderExt(models.Model):
            _inherit = "sale.order"

            def action_my_custom(self):
                return True
    """))
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="view_sale_btn" model="ir.ui.view">
    <field name="model">sale.order</field>
    <field name="arch" type="xml">
      <form><button name="action_my_custom" type="object"/></form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["ext_method"]
    assert check_button_method_not_found(ctx) == []


def test_subview_field_not_flagged_against_parent_repo_model(tmp_path: Path):
    """A repo-complete parent model must not flag a subview field that belongs to a comodel."""
    mod = tmp_path / "subview_mod"
    (mod / "models").mkdir(parents=True)
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "models" / "m.py").write_text(dedent("""\
        from odoo import models, fields

        class Parent(models.Model):
            _name = "my.parent"
            line_ids = fields.One2many("my.line", "parent_id")

        class Line(models.Model):
            _name = "my.line"
            parent_id = fields.Many2one("my.parent")
            qty = fields.Float()
    """))
    (mod / "views" / "v.xml").write_text("""\
<odoo>
  <record id="view_parent_form" model="ir.ui.view">
    <field name="model">my.parent</field>
    <field name="arch" type="xml">
      <form>
        <field name="line_ids">
          <tree><field name="qty"/></tree>
        </field>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["subview_mod"]
    # Without A5, 'qty' would be checked against my.parent (provably complete) -> false NOT_FOUND.
    assert check_view_field_not_in_model(ctx) == []
