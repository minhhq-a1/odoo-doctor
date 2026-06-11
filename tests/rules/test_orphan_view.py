"""orphan-view flags views that nothing references."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.orphan_view import check_orphan_view


def _manifest(files: list[str]) -> str:
    joined = ", ".join(f'"{f}"' for f in files)
    return '{"name": "M", "depends": [], "data": [%s], "license": "LGPL-3"}' % joined


def test_unreferenced_view_is_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "views" / "v.xml").write_text(
        """<odoo>
  <record id="orphan_form" model="ir.ui.view">
    <field name="model">my.model</field>
    <field name="arch" type="xml"><form/></field>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_orphan_view(ctx)
    assert any(d.rule == "orphan-view" for d in diags)


def test_view_referenced_by_action_is_not_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "views" / "v.xml").write_text(
        """<odoo>
  <record id="used_form" model="ir.ui.view">
    <field name="model">my.model</field>
    <field name="arch" type="xml"><form/></field>
  </record>
  <record id="act" model="ir.actions.act_window">
    <field name="view_id" ref="used_form"/>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_orphan_view(ctx)
    assert not any(d.rule == "orphan-view" for d in diags)
