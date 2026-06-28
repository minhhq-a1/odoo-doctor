"""Tests for Frontend rules."""

from __future__ import annotations


def _make_addon_with_assets(tmp_path, name, assets_dict, create_files=None):
    """Helper to create a test addon with manifest assets."""
    mod = tmp_path / name
    mod.mkdir()

    manifest = {
        "name": name,
        "version": "17.0.1.0.0",
        "depends": ["base"],
        "data": [],
        "license": "LGPL-3",
        "assets": assets_dict,
    }
    (mod / "__manifest__.py").write_text(repr(manifest))

    if create_files:
        for f in create_files:
            full = mod / f
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("/* content */")

    return mod


def test_asset_bundle_missing_flags_nonexistent(tmp_path):
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    _make_addon_with_assets(
        tmp_path,
        "test_mod",
        {"web.assets_backend": ["test_mod/static/src/js/missing.js"]},
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_asset_bundle_missing(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "asset-bundle-missing"
    assert "missing.js" in diags[0].title


def test_asset_bundle_missing_clean_when_exists(tmp_path):
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    _make_addon_with_assets(
        tmp_path,
        "test_mod",
        {"web.assets_backend": ["test_mod/static/src/js/app.js"]},
        create_files=["static/src/js/app.js"],
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_asset_bundle_missing(ctx)
    assert diags == []


def test_asset_bundle_missing_skips_glob_patterns(tmp_path):
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    _make_addon_with_assets(
        tmp_path,
        "test_mod",
        {"web.assets_backend": ["test_mod/static/src/**/*.js"]},
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_asset_bundle_missing(ctx)
    assert diags == []


def test_asset_bundle_missing_skips_other_modules(tmp_path):
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    _make_addon_with_assets(
        tmp_path,
        "test_mod",
        {"web.assets_backend": ["other_module/static/src/js/app.js"]},
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_asset_bundle_missing(ctx)
    assert diags == []


def test_asset_bundle_missing_no_assets(tmp_path):
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "test_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "test_mod", "version": "17.0.1.0.0",'
        ' "depends": ["base"], "data": [], "license": "LGPL-3"}'
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_asset_bundle_missing(ctx)
    assert diags == []
