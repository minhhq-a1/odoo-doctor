# tests/graph/test_source_index.py
"""Tests for Odoo source path indexing."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.source_index import build_source_index
from odoo_doctor.graph.resolver import ResolveResult, SymbolResolver


def test_build_source_index(tmp_path: Path):
    # Setup mock Odoo source structure:
    # tmp_path/addons/mock_sale/__manifest__.py
    # tmp_path/addons/mock_sale/models/sale.py
    # tmp_path/addons/mock_sale/data.xml
    mock_addon = tmp_path / "addons" / "mock_sale"
    mock_addon.mkdir(parents=True)

    (mock_addon / "__manifest__.py").write_text(
        '{"name": "Mock Sale", "depends": ["base"], "data": ["data.xml"]}'
    )

    models_dir = mock_addon / "models"
    models_dir.mkdir()
    (models_dir / "sale.py").write_text(
        dedent("""\
        from odoo import models
        
        class MockSaleOrder(models.Model):
            _name = "mock.sale.order"
    """)
    )

    (mock_addon / "data.xml").write_text(
        dedent("""\
        <odoo>
            <record id="mock_record" model="mock.sale.order">
                <field name="name">Record</field>
            </record>
        </odoo>
    """)
    )

    index = build_source_index(tmp_path)

    # Verify model indexing
    assert "mock.sale.order" in index.model_owners
    assert index.model_owners["mock.sale.order"] == "mock_sale"


def test_build_source_index_from_direct_addons_root(tmp_path: Path):
    mock_addon = tmp_path / "direct_mod"
    mock_addon.mkdir()
    (mock_addon / "__manifest__.py").write_text('{"name": "Direct", "data": []}')
    models_dir = mock_addon / "models"
    models_dir.mkdir()
    (models_dir / "direct.py").write_text(
        dedent("""\
        from odoo import models

        class DirectModel(models.Model):
            _name = "direct.model"
    """)
    )

    index = build_source_index(tmp_path)

    assert index.model_owners["direct.model"] == "direct_mod"


def test_build_source_index_from_odoo_addons_layout(tmp_path: Path):
    mock_addon = tmp_path / "odoo" / "addons" / "mock_core"
    mock_addon.mkdir(parents=True)
    (mock_addon / "__manifest__.py").write_text('{"name": "Mock Core", "data": []}')
    models_dir = mock_addon / "models"
    models_dir.mkdir()
    (models_dir / "core.py").write_text(
        dedent("""\
        from odoo import models

        class CoreModel(models.Model):
            _name = "core.model"
    """)
    )

    index = build_source_index(tmp_path)

    assert index.model_owners["core.model"] == "mock_core"


def test_resolver_with_source_index(tmp_path: Path):
    mock_addon = tmp_path / "addons" / "mock_sale"
    mock_addon.mkdir(parents=True)
    (mock_addon / "__manifest__.py").write_text(
        '{"name": "Mock Sale", "data": ["data.xml"]}'
    )

    models_dir = mock_addon / "models"
    models_dir.mkdir()
    (models_dir / "sale.py").write_text(
        'class X(models.Model):\n    _name = "mock.model"'
    )

    (mock_addon / "data.xml").write_text(
        '<odoo><record id="mock_rec" model="mock.model"/></odoo>'
    )

    resolver = SymbolResolver(
        repo_models={},
        repo_xml_ids={},
        stub_version="17.0",
        source_path=str(tmp_path),
    )

    # Test resolve_model via source_path
    res_model = resolver.resolve_model("mock.model")
    assert res_model.status == ResolveResult.FOUND
    assert res_model.source == "source_path"

    # Test resolve_xml_id via source_path -> should be UNKNOWN (xml resolution deferred)
    res_xml = resolver.resolve_xml_id("mock_sale.mock_rec")
    assert res_xml.status == ResolveResult.UNKNOWN

    # Test owner_module_for_model via source_path
    owner = resolver.owner_module_for_model("mock.model")
    assert owner.status == ResolveResult.FOUND
    assert owner.source == "mock_sale"
