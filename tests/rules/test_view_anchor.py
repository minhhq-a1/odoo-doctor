"""A view ref inserted next to a node that is not a field of the model sits in a subview."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found
from odoo_doctor.rules.xml.view_field_not_in_model import (
    check_view_field_not_in_model,
)

MODEL = """from odoo import fields, models

class X(models.Model):
    _name = 'x.model'
    _description = 'X'

    alpha = fields.Char()

    def action_known(self):
        return True
"""

VIEW = """<odoo>
  <record id="view_x_inherit" model="ir.ui.view">
    <field name="model">x.model</field>
    <field name="inherit_id" ref="base.some_view"/>
    <field name="arch" type="xml">
      <data>
        <xpath expr="//field[@name='{anchor}']" position="after">
          <field name="unknown_field"/>
          <button name="action_unknown" type="object"/>
        </xpath>
      </data>
    </field>
  </record>
</odoo>
"""


def _module(tmp_path: Path, anchor: str):
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "views").mkdir()
    (addon / "views" / "v.xml").write_text(VIEW.format(anchor=anchor))
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": "mod",
                "version": "17.0.1.0.0",
                "depends": [],
                "data": ["views/v.xml"],
                "license": "LGPL-3",
            }
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("from . import m\n")
    (addon / "models" / "m.py").write_text(MODEL)
    return build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]


@pytest.mark.parametrize("anchor", ["pattern", "line_only_column"])
def test_refs_next_to_a_node_that_is_not_a_field_of_the_model_are_not_checked(
    tmp_path: Path, anchor: str
):
    # `pattern` is not a field of x.model, so the node it names lives in a subview
    ctx = _module(tmp_path, anchor)
    assert check_view_field_not_in_model(ctx) == []
    assert check_button_method_not_found(ctx) == []


def test_refs_next_to_a_field_of_the_model_are_still_checked(tmp_path: Path):
    ctx = _module(tmp_path, "alpha")
    fields = check_view_field_not_in_model(ctx)
    buttons = check_button_method_not_found(ctx)
    assert [d.title for d in fields] == [
        "View references unknown field 'unknown_field'"
    ]
    assert [d.title for d in buttons] == [
        "Button calls unknown method 'action_unknown'"
    ]
