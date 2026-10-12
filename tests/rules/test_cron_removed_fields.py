"""cron-removed-fields: ir.cron lost numbercall and doall in Odoo 18."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.upgrade_safety.cron_removed_fields import (
    check_cron_removed_fields,
)

CRON = """<odoo>
    <record id="ir_cron_job" model="ir.cron">
        <field name="name">Job</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="numbercall">{numbercall}</field>
        <field name="doall" eval="False"/>
    </record>
    <record id="other" model="ir.actions.server">
        <field name="name">Other</field>
        <field name="numbercall">1</field>
    </record>
</odoo>
"""


def _diags(tmp_path: Path, xml: str, version: str = "18.0", file="data/cron.xml"):
    addon = tmp_path / "mod"
    (addon / "data").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": "mod",
                "version": f"{version}.1.0.0",
                "depends": [],
                "license": "LGPL-3",
                "data": [file],
            }
        )
    )
    (addon / "__init__.py").write_text("")
    (addon / file).write_text(xml)
    ctx = build_project_graph([tmp_path], odoo_version=version).modules["mod"]
    return check_cron_removed_fields(ctx)


def test_numbercall_and_doall_on_ir_cron_are_flagged(tmp_path: Path):
    diags = _diags(tmp_path, CRON.format(numbercall="-1"))
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "cron-removed-fields",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert d.line == 6  # first removed field
    assert "numbercall" in d.message and "doall" in d.message


def test_a_limited_numbercall_is_explained(tmp_path: Path):
    d = _diags(tmp_path, CRON.format(numbercall="3"))[0]
    assert "3" in d.message and "repeat" in d.message


def test_other_models_with_the_same_field_name_are_not_flagged(tmp_path: Path):
    xml = """<odoo><record id="a" model="ir.actions.server">
        <field name="numbercall">1</field></record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_cron_without_the_removed_fields_is_clean(tmp_path: Path):
    xml = """<odoo><record id="a" model="ir.cron">
        <field name="interval_number">1</field></record></odoo>"""
    assert _diags(tmp_path, xml) == []


def test_malformed_xml_is_skipped(tmp_path: Path):
    assert _diags(tmp_path, "<odoo><record") == []


def test_rule_only_runs_from_odoo_18():
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m for m, _ in default_registry.get_rules() if m.name == "cron-removed-fields"
    )
    assert meta.min_version == "18.0"
