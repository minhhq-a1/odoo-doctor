# tests/graph/test_complete_stub.py
"""Stub completeness flag: partial stubs cannot prove absence; complete stubs can."""

from __future__ import annotations

import json

from odoo_doctor.graph.stubs import loader
from odoo_doctor.graph.stubs.loader import StubData, load_stubs


def test_bundled_stub_is_partial():
    """Bundled 17.0 stub omits 'complete' -> defaults to partial (False)."""
    stubs = load_stubs("17.0")
    assert stubs is not None
    assert stubs.complete is False


def test_stubdata_complete_defaults_false():
    sd = StubData(version="x", models={}, xml_ids={})
    assert sd.complete is False


def test_loader_reads_complete_true(tmp_path, monkeypatch):
    stub_file = tmp_path / "42.0.json"
    stub_file.write_text(
        json.dumps(
            {
                "version": "42.0",
                "complete": True,
                "models": {"my.model": {"fields": ["a"], "methods": ["m"]}},
                "xml_ids": {},
            }
        )
    )
    monkeypatch.setattr(loader, "_STUBS_DIR", tmp_path)
    stubs = load_stubs("42.0")
    assert stubs is not None
    assert stubs.complete is True


def test_complete_stub_proves_absence(monkeypatch):
    """When the stub file is complete, a missing field IS provably NOT_FOUND."""
    from odoo_doctor.graph.resolver import SymbolResolver
    from odoo_doctor.graph.resolver import ResolveResult

    r = SymbolResolver(repo_models={}, repo_xml_ids={}, stub_version="17.0")
    # Simulate a complete stub backing (e.g. build_stubs source output).
    r._stubs.complete = True
    assert r.resolve_field("sale.order", "name").status == ResolveResult.FOUND
    assert r.resolve_field("sale.order", "zzz_nope").status == ResolveResult.NOT_FOUND
    assert r.resolve_method("sale.order", "zzz_nope").status == ResolveResult.NOT_FOUND
