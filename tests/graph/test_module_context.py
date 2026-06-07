# tests/graph/test_module_context.py
"""Tests for ModuleContext builder."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph


def test_build_project_graph(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon],
        odoo_version="17.0",
        odoo_source_path=None,
    )
    assert len(graph.modules) == 1
    ctx = graph.modules["sample_addon"]
    assert ctx.name == "sample_addon"
    assert "sale" in ctx.depends
    assert ctx.resolver is graph.resolver  # shared reference


def test_module_context_has_parsed_data(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon],
        odoo_version="17.0",
    )
    ctx = graph.modules["sample_addon"]
    # Should have parsed models
    assert len(ctx.models) > 0
    # Should have parsed XML IDs
    assert len(ctx.xml_ids) > 0
    assert len(ctx.xml_records) >= len(ctx.xml_ids)
    # Should have parsed views
    assert len(ctx.views) > 0
    # Should have parsed access rules
    assert len(ctx.access_rules) > 0


def test_resolver_uses_manifest_version_for_stubs_when_project_unknown(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon],
        odoo_version="unknown",
    )
    result = graph.resolver.resolve_model("sale.order")
    from odoo_doctor.graph.resolver import ResolveResult
    assert result.status == ResolveResult.FOUND
