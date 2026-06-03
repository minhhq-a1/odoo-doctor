# tests/graph/test_resolver.py
"""Tests for stub loading and confidence-aware symbol resolver."""

from __future__ import annotations

from odoo_doctor.graph.stubs.loader import StubData, load_stubs


def test_load_stubs_17():
    stubs = load_stubs("17.0")
    assert stubs is not None
    assert "res.partner" in stubs.models
    assert "name" in stubs.models["res.partner"]["fields"]
    assert "base.main_company" in stubs.xml_ids


def test_load_stubs_unknown_version():
    stubs = load_stubs("99.0")
    assert stubs is None


# --- Resolver tests ---

from odoo_doctor.graph.resolver import ResolveResult, SymbolLookup, SymbolResolver
from odoo_doctor.parsers.python_models import FieldInfo, ModelInfo


def _make_resolver(repo_models=None, stub_version="17.0", source_path=None):
    return SymbolResolver(
        repo_models=repo_models or {},
        repo_xml_ids={},
        stub_version=stub_version,
        source_path=source_path,
    )


def test_resolve_field_from_repo():
    models = {
        "sale.custom": ModelInfo(
            name="sale.custom", file_path="f.py", line=1,
            fields={"my_field": FieldInfo(name="my_field", field_type="Char")},
        )
    }
    r = _make_resolver(repo_models=models)
    result = r.resolve_field("sale.custom", "my_field")
    assert result.status == ResolveResult.FOUND
    assert result.source == "repo"


def test_resolve_field_from_stub():
    r = _make_resolver()
    result = r.resolve_field("res.partner", "name")
    assert result.status == ResolveResult.FOUND
    assert result.source == "stub"


def test_resolve_field_not_found():
    """Field proven to not exist on a known model."""
    r = _make_resolver()
    result = r.resolve_field("res.partner", "zzz_nonexistent_field")
    assert result.status == ResolveResult.NOT_FOUND


def test_resolve_field_unknown_model():
    """Model not in repo or stubs -> UNKNOWN, not NOT_FOUND."""
    r = _make_resolver()
    result = r.resolve_field("totally.unknown.model", "any_field")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_model_found_in_stub():
    r = _make_resolver()
    result = r.resolve_model("sale.order")
    assert result.status == ResolveResult.FOUND


def test_resolve_model_unknown():
    r = _make_resolver()
    result = r.resolve_model("zzz.nonexistent")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_method_found():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "action_confirm")
    assert result.status == ResolveResult.FOUND


def test_resolve_method_not_found():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "zzz_method")
    assert result.status == ResolveResult.NOT_FOUND


def test_resolve_xml_id_found():
    r = _make_resolver()
    result = r.resolve_xml_id("base.main_company")
    assert result.status == ResolveResult.FOUND


def test_resolve_xml_id_unknown():
    r = _make_resolver()
    result = r.resolve_xml_id("nonexistent.xml_id")
    assert result.status == ResolveResult.UNKNOWN


def test_golden_rule_unknown_is_not_not_found():
    """The golden rule: UNKNOWN must never be treated as NOT_FOUND."""
    r = _make_resolver()
    field_result = r.resolve_field("unknown.model", "any_field")
    assert field_result.status != ResolveResult.NOT_FOUND
    assert field_result.status == ResolveResult.UNKNOWN
