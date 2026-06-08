# tests/graph/test_build_stubs.py
"""Tests for build_stubs.py AST extraction."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.stubs.build_stubs import (
    _extract_class_data,
    parse_odoo_source,
    parse_odoo_xml_ids,
)
import ast


def _cls(src: str) -> ast.ClassDef:
    tree = ast.parse(dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))


def test_extract_name_and_field():
    node = _cls("""\
        class SaleOrder(models.Model):
            _name = "sale.order"
            name = fields.Char()
            amount = fields.Float()
    """)
    name, fields, methods = _extract_class_data(node)
    assert name == "sale.order"
    assert "name" in fields
    assert "amount" in fields


def test_extract_skips_private_fields():
    node = _cls("""\
        class M(models.Model):
            _name = "m"
            _sql_constraints = []
            name = fields.Char()
    """)
    _, fields, _ = _extract_class_data(node)
    assert "_sql_constraints" not in fields
    assert "name" in fields


def test_extract_methods():
    node = _cls("""\
        class M(models.Model):
            _name = "m"

            def action_confirm(self):
                pass

            def _compute_name(self):
                pass

            def __repr__(self):
                pass
    """)
    _, _, methods = _extract_class_data(node)
    assert "action_confirm" in methods
    assert "_compute_name" in methods
    assert "__repr__" not in methods


def test_extract_inherit_only_returns_none_name():
    node = _cls("""\
        class SaleOrderExt(models.Model):
            _inherit = "sale.order"
            custom_note = fields.Char()
    """)
    name, fields, _ = _extract_class_data(node)
    assert name is None
    assert "custom_note" in fields


def test_extract_attribute_fields_call():
    """fields.Many2one() via attribute access."""
    node = _cls("""\
        class M(models.Model):
            _name = "m"
            partner_id = fields.Many2one("res.partner")
    """)
    _, fields, _ = _extract_class_data(node)
    assert "partner_id" in fields


def test_parse_odoo_source_from_fixtures(tmp_path: Path):
    """parse_odoo_source finds models in a small synthetic source tree."""
    addons = tmp_path / "addons"
    (addons / "sale" / "models").mkdir(parents=True)
    (addons / "sale" / "models" / "sale_order.py").write_text(
        dedent("""\
        from odoo import models, fields

        class SaleOrder(models.Model):
            _name = "sale.order"
            name = fields.Char()
            partner_id = fields.Many2one("res.partner")

            def action_confirm(self):
                pass
    """)
    )

    models = parse_odoo_source(tmp_path)
    assert "sale.order" in models
    assert "name" in models["sale.order"]["fields"]
    assert "partner_id" in models["sale.order"]["fields"]
    assert "action_confirm" in models["sale.order"]["methods"]


def test_parse_odoo_source_skips_tests(tmp_path: Path):
    """Test files should not be parsed."""
    tests_dir = tmp_path / "addons" / "sale" / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_sale.py").write_text(
        dedent("""\
        from odoo import models, fields

        class FakeModel(models.Model):
            _name = "fake.model"
            name = fields.Char()
    """)
    )

    models = parse_odoo_source(tmp_path)
    assert "fake.model" not in models


def test_parse_odoo_source_merges_inherit(tmp_path: Path):
    """Fields from _inherit classes are merged into primary model."""
    addons = tmp_path / "addons"
    (addons / "base" / "models").mkdir(parents=True)
    (addons / "base" / "models" / "res_partner.py").write_text(
        dedent("""\
        from odoo import models, fields

        class ResPartner(models.Model):
            _name = "res.partner"
            name = fields.Char()
    """)
    )
    (addons / "sale" / "models").mkdir(parents=True)
    (addons / "sale" / "models" / "res_partner.py").write_text(
        dedent("""\
        from odoo import models, fields

        class ResPartnerSale(models.Model):
            _inherit = "res.partner"
            sale_order_count = fields.Integer()
    """)
    )

    models = parse_odoo_source(tmp_path)
    assert "res.partner" in models
    assert "name" in models["res.partner"]["fields"]
    assert "sale_order_count" in models["res.partner"]["fields"]


def test_parse_xml_ids(tmp_path: Path):
    """parse_odoo_xml_ids extracts XML IDs from data files."""
    data_dir = tmp_path / "addons" / "sale" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "sale_data.xml").write_text("""\
<odoo>
  <record id="sale_menu_root" model="ir.ui.menu">
    <field name="name">Sales</field>
  </record>
  <record id="view_order_form" model="ir.ui.view">
    <field name="name">sale.order.form</field>
  </record>
</odoo>
""")
    xml_ids = parse_odoo_xml_ids(tmp_path)
    assert "sale.sale_menu_root" in xml_ids
    assert xml_ids["sale.sale_menu_root"] == "ir.ui.menu"
    assert "sale.view_order_form" in xml_ids


def test_build_stubs_cli_source_mode(tmp_path: Path):
    """CLI source mode writes JSON output."""
    addons = tmp_path / "addons"
    (addons / "sale" / "models").mkdir(parents=True)
    (addons / "sale" / "models" / "sale.py").write_text(
        dedent("""\
        from odoo import models, fields

        class SaleOrder(models.Model):
            _name = "sale.order"
            name = fields.Char()
    """)
    )

    out = tmp_path / "out.json"
    from odoo_doctor.graph.stubs.build_stubs import main

    main(
        [
            "source",
            "--odoo-path",
            str(tmp_path),
            "--version",
            "17.0",
            "--output",
            str(out),
        ]
    )

    import json

    data = json.loads(out.read_text())
    assert data["version"] == "17.0"
    assert "sale.order" in data["models"]
