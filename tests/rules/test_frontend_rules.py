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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

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


def _asset_diags(tmp_path, assets, create_files=None):
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.frontend.asset_bundle_missing import (
        check_asset_bundle_missing,
    )

    _make_addon_with_assets(tmp_path, "test_mod", assets, create_files)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    return check_asset_bundle_missing(graph.modules["test_mod"])


def test_asset_bundle_missing_accepts_directive_tuples(tmp_path):
    """Odoo 15+ lets a bundle hold `('include', bundle)` style directives; the rule used
    to crash on them (`'tuple' object has no attribute 'startswith'`)."""
    diags = _asset_diags(
        tmp_path,
        {
            "web.assets_backend": [
                ("include", "web._assets_helpers"),
                ("remove", "web/static/src/legacy/old.js"),
                ("prepend", "test_mod/static/src/js/first.js"),
                ("append", "test_mod/static/src/js/last.js"),
                ("before", "web/static/src/a.js", "test_mod/static/src/js/b.js"),
                ("after", "web/static/src/a.js", "test_mod/static/src/js/c.js"),
                ("replace", "web/static/src/a.js", "test_mod/static/src/js/d.js"),
            ]
        },
        create_files=[
            "static/src/js/first.js",
            "static/src/js/last.js",
            "static/src/js/b.js",
            "static/src/js/c.js",
            "static/src/js/d.js",
        ],
    )
    assert diags == []


def test_asset_bundle_missing_checks_the_file_a_directive_adds(tmp_path):
    diags = _asset_diags(
        tmp_path,
        {
            "web.assets_backend": [
                ("prepend", "test_mod/static/src/js/gone1.js"),
                ("append", "test_mod/static/src/js/gone2.js"),
                ("before", "web/static/src/a.js", "test_mod/static/src/js/gone3.js"),
                ("after", "web/static/src/a.js", "test_mod/static/src/js/gone4.js"),
                ("replace", "web/static/src/a.js", "test_mod/static/src/js/gone5.js"),
                "test_mod/static/src/js/gone6.js",
            ]
        },
    )
    assert sorted(d.title.rsplit("/", 1)[-1] for d in diags) == [
        f"gone{i}.js" for i in range(1, 7)
    ]


def test_asset_bundle_missing_ignores_directives_it_cannot_read(tmp_path):
    diags = _asset_diags(
        tmp_path,
        {
            "web.assets_backend": [
                ("prepend",),
                ("mystery", "test_mod/static/src/js/x.js"),
                ["include", "web.assets_x"],
                None,
                42,
            ],
            "web.assets_frontend": "not-a-list",
        },
    )
    assert diags == []
