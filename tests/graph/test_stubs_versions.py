# tests/graph/test_stubs_versions.py
"""Tests for 18.0 and 19.0 stubs."""

from __future__ import annotations

from odoo_doctor.graph.stubs.loader import load_stubs


def test_stubs_18_loads():
    stubs = load_stubs("18.0")
    assert stubs is not None
    assert stubs.version == "18.0"


def test_stubs_18_has_invoice_status():
    """18.0 adds invoice_status to sale.order."""
    stubs = load_stubs("18.0")
    assert "sale.order" in stubs.models
    assert "invoice_status" in stubs.models["sale.order"]["fields"]


def test_stubs_18_has_payment_state():
    """18.0 adds payment_state to account.move."""
    stubs = load_stubs("18.0")
    assert "payment_state" in stubs.models["account.move"]["fields"]


def test_stubs_18_has_discuss_channel():
    """18.0 introduces discuss.channel."""
    stubs = load_stubs("18.0")
    assert "discuss.channel" in stubs.models


def test_stubs_19_loads():
    stubs = load_stubs("19.0")
    assert stubs is not None
    assert stubs.version == "19.0"


def test_stubs_19_has_spreadsheet_template():
    """19.0 introduces spreadsheet.template."""
    stubs = load_stubs("19.0")
    assert "spreadsheet.template" in stubs.models


def test_stubs_19_has_analytic_distribution():
    """19.0 uses analytic_distribution instead of analytic_account_id on move lines."""
    stubs = load_stubs("19.0")
    assert "analytic_distribution" in stubs.models["account.move.line"]["fields"]


def test_stubs_unknown_version_returns_none():
    stubs = load_stubs("15.0")
    assert stubs is None


def test_stubs_version_prefix_fallback():
    """18.0.1 should resolve to 18.0."""
    stubs = load_stubs("18.0.1")
    assert stubs is not None
    assert stubs.version == "18.0"


def test_resolver_uses_18_stubs_correctly():
    """Resolver with 18.0 version can resolve sale.order.invoice_status."""
    from odoo_doctor.graph.resolver import ResolveResult, SymbolResolver

    resolver = SymbolResolver(
        repo_models={},
        repo_xml_ids={},
        stub_version="18.0",
    )
    result = resolver.resolve_field("sale.order", "invoice_status")
    assert result.status == ResolveResult.FOUND
    assert result.source == "stub"


def test_resolver_uses_19_stubs_correctly():
    """Resolver with 19.0 can resolve spreadsheet.template."""
    from odoo_doctor.graph.resolver import ResolveResult, SymbolResolver

    resolver = SymbolResolver(
        repo_models={},
        repo_xml_ids={},
        stub_version="19.0",
    )
    result = resolver.resolve_model("spreadsheet.template")
    assert result.status == ResolveResult.FOUND
    assert result.source == "stub"
