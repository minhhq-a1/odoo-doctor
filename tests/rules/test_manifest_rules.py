# tests/rules/test_manifest_rules.py
"""Tests for manifest rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph


def test_missing_required_fields_clean(sample_addon: Path):
    from odoo_doctor.rules.manifest.missing_required_fields import (
        check_missing_required_fields,
    )

    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_missing_required_fields(ctx)
    assert diags == []


def test_missing_required_fields_catches(tmp_path: Path):
    from odoo_doctor.rules.manifest.missing_required_fields import (
        check_missing_required_fields,
    )

    mod = tmp_path / "incomplete_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Incomplete"}')
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["incomplete_mod"]
    diags = check_missing_required_fields(ctx)
    rule_names = [d.rule for d in diags]
    assert all(r == "manifest-missing-required-fields" for r in rule_names)
    missing = {d.title.rsplit(": ", 1)[-1].strip("'") for d in diags}
    assert missing == {"version", "depends", "data", "installable", "license"}


def test_missing_dependency_catches_sale(tmp_path: Path):
    from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency

    # A module that inherits sale.order but doesn't declare 'sale' in depends
    mod = tmp_path / "missing_dep"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "Missing Dep", "version": "17.0.1.0.0", "depends": ["base"], "data": [], "license": "LGPL-3"}'
    )
    models_dir = mod / "models"
    models_dir.mkdir()
    (models_dir / "sale_ext.py").write_text(
        dedent("""\
        from odoo import models

        class SaleExt(models.Model):
            _inherit = "sale.order"
    """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["missing_dep"]
    diags = check_missing_dependency(ctx)
    assert any(d.rule == "manifest-missing-dependency" for d in diags)


def test_missing_dependency_clean_when_sale_in_depends(tmp_path: Path):
    from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency

    mod = tmp_path / "ok_dep"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "OK Dep", "version": "17.0.1.0.0", "depends": ["sale"], "data": [], "license": "LGPL-3"}'
    )
    models_dir = mod / "models"
    models_dir.mkdir()
    (models_dir / "sale_ext.py").write_text(
        dedent("""\
        from odoo import models

        class SaleExt(models.Model):
            _inherit = "sale.order"
    """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["ok_dep"]
    diags = check_missing_dependency(ctx)
    assert diags == []


def test_missing_dependency_from_xml_ref(tmp_path: Path):
    from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency

    mod = tmp_path / "xml_dep"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "XML Dep", "version": "17.0.1.0.0", "depends": ["base"], "data": ["views.xml"], "license": "LGPL-3"}'
    )
    (mod / "views.xml").write_text(
        dedent("""\
        <odoo>
            <record id="view_test" model="ir.ui.view">
                <field name="name">test</field>
                <field name="model">sale.order</field>
                <field name="inherit_id" ref="sale.view_order_form"/>
            </record>
            <record id="another_test" model="ir.ui.view">
                <field name="name">another</field>
                <!-- direct ref to sale -->
                <field name="model" ref="sale.model_sale_order"/>
            </record>
        </odoo>
    """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["xml_dep"]
    diags = check_missing_dependency(ctx)
    # Check that 'sale' is detected as missing
    diag_rules = [d.rule for d in diags]
    assert "manifest-missing-dependency" in diag_rules
    # Verify aggregation
    diag_sale = [
        d
        for d in diags
        if d.rule == "manifest-missing-dependency" and "sale" in d.message
    ]
    assert len(diag_sale) == 1
    assert "sale.view_order_form" in diag_sale[0].message
    assert "sale.model_sale_order" in diag_sale[0].message


def test_missing_dependency_ignores_unknown_module_ref(tmp_path):
    from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency

    mod = tmp_path / "typo_dep"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name":"Typo","version":"17.0.1.0.0","depends":["base"],"data":["v.xml"],"license":"LGPL-3"}'
    )
    (mod / "v.xml").write_text(
        '<odoo><record id="r" model="ir.ui.view">'
        '<field name="x" ref="nonexistent_module_xyz.some_view"/></record></odoo>'
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["typo_dep"]
    diags = check_missing_dependency(ctx)
    assert all("nonexistent_module_xyz" not in d.message for d in diags)
