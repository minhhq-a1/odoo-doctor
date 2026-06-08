from odoo_doctor.core.config import _build_config, SurfaceConfig
from odoo_doctor.core.surfaces import filter_for_surface
from odoo_doctor.core.diagnostics import Diagnostic


def test_surfaces_defaults_when_absent():
    cfg = _build_config({})
    assert "pr_comment" in cfg.surfaces
    assert "ci_failure" in cfg.surfaces

    assert cfg.surfaces["pr_comment"].min_confidence is None
    assert cfg.surfaces["pr_comment"].categories == []

    assert cfg.surfaces["ci_failure"].min_confidence == "high"
    assert cfg.surfaces["ci_failure"].categories == []


def test_surfaces_parsed_from_toml():
    raw = {
        "surfaces": {
            "pr_comment": {"min_confidence": "medium", "categories": []},
            "ci_failure": {
                "min_confidence": "high",
                "categories": ["Security", "Correctness"],
            },
        }
    }
    cfg = _build_config(raw)
    assert cfg.surfaces["pr_comment"].min_confidence == "medium"
    assert cfg.surfaces["pr_comment"].categories == []
    assert cfg.surfaces["ci_failure"].min_confidence == "high"
    assert cfg.surfaces["ci_failure"].categories == ["Security", "Correctness"]


def test_filter_for_surface_drops_below_min_confidence():
    high_diag = Diagnostic(
        "m", "f", 1, 1, "r", "c", "info", "P1", "s", "high", "t", "m", "h", "17"
    )
    low_diag = Diagnostic(
        "m", "f", 1, 1, "r", "c", "info", "P1", "s", "low", "t", "m", "h", "17"
    )

    cfg = SurfaceConfig(min_confidence="medium")
    filtered = filter_for_surface([high_diag, low_diag], cfg)

    assert len(filtered) == 1
    assert filtered[0].confidence == "high"


def test_filter_for_surface_filters_by_category():
    d1 = Diagnostic(
        "m", "f", 1, 1, "r", "Security", "info", "P1", "s", "high", "t", "m", "h", "17"
    )
    d2 = Diagnostic(
        "m",
        "f",
        1,
        1,
        "r",
        "Performance",
        "info",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )

    cfg = SurfaceConfig(categories=["Security"])
    filtered = filter_for_surface([d1, d2], cfg)

    assert len(filtered) == 1
    assert filtered[0].category == "Security"


def test_filter_for_surface_empty_categories_keeps_all():
    d1 = Diagnostic(
        "m", "f", 1, 1, "r", "Security", "info", "P1", "s", "high", "t", "m", "h", "17"
    )
    d2 = Diagnostic(
        "m",
        "f",
        1,
        1,
        "r",
        "Performance",
        "info",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )

    cfg = SurfaceConfig(categories=[])
    filtered = filter_for_surface([d1, d2], cfg)

    assert len(filtered) == 2
