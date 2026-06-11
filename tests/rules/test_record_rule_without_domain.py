"""record-rule-without-domain flags ir.rule records lacking a real domain."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.record_rule_without_domain import (
    check_record_rule_without_domain,
)


def _manifest(files: list[str]) -> str:
    joined = ", ".join(f'"{f}"' for f in files)
    return '{"name": "M", "depends": [], "data": [%s], "license": "LGPL-3"}' % joined


def test_rule_without_domain_force_is_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "security").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["security/rules.xml"]))
    (mod / "security" / "rules.xml").write_text(
        """<odoo>
  <record id="rule_all" model="ir.rule">
    <field name="name">All</field>
    <field name="model_id" ref="model_my_model"/>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_record_rule_without_domain(ctx)
    assert any(d.rule == "record-rule-without-domain" for d in diags)


def test_empty_domain_force_is_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "security").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["security/rules.xml"]))
    (mod / "security" / "rules.xml").write_text(
        """<odoo>
  <record id="rule_empty" model="ir.rule">
    <field name="domain_force">[]</field>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_record_rule_without_domain(ctx)
    assert any(d.rule == "record-rule-without-domain" for d in diags)


def test_rule_with_domain_is_not_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "security").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["security/rules.xml"]))
    (mod / "security" / "rules.xml").write_text(
        """<odoo>
  <record id="rule_scoped" model="ir.rule">
    <field name="domain_force">[('user_id','=',user.id)]</field>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_record_rule_without_domain(ctx)
    assert not any(d.rule == "record-rule-without-domain" for d in diags)
