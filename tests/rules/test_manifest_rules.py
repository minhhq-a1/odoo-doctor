# tests/rules/test_manifest_rules.py
"""Tests for manifest rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph


def test_missing_required_fields_clean(sample_addon: Path):
    from odoo_doctor.rules.manifest.missing_required_fields import check_missing_required_fields
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_missing_required_fields(ctx)
    assert diags == []


def test_missing_required_fields_catches(tmp_path: Path):
    from odoo_doctor.rules.manifest.missing_required_fields import check_missing_required_fields
    mod = tmp_path / "incomplete_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Incomplete"}')
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["incomplete_mod"]
    diags = check_missing_required_fields(ctx)
    rule_names = [d.rule for d in diags]
    assert all(r == "manifest-missing-required-fields" for r in rule_names)
    # Should flag: version, depends, license (name is present)
    assert len(diags) >= 2


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
    (models_dir / "sale_ext.py").write_text(dedent("""\
        from odoo import models

        class SaleExt(models.Model):
            _inherit = "sale.order"
    """))
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
    (models_dir / "sale_ext.py").write_text(dedent("""\
        from odoo import models

        class SaleExt(models.Model):
            _inherit = "sale.order"
    """))
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["ok_dep"]
    diags = check_missing_dependency(ctx)
    assert diags == []
