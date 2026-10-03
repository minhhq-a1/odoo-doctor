"""Default CI policy: --fail-on only counts P0/P1 high-confidence findings."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app
from odoo_doctor.core.config import _build_config
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.surfaces import filter_for_surface

runner = CliRunner()

_BASE_CONFIG = (
    '[odoo-doctor]\nodoo_version = "17.0"\n'
    "[adapters]\nruff = false\npylint_odoo = false\n"
)


def _p2_error_addon(root: Path, extra_config: str = "") -> Path:
    """An addon whose only finding is asset-bundle-missing (P2, severity error)."""
    mod = root / "addons" / "m"
    mod.mkdir(parents=True)
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        "{'name': 'M', 'version': '17.0.1.0.0', 'depends': ['base'], 'data': [], "
        "'installable': True, 'license': 'LGPL-3', "
        "'assets': {'web.assets_backend': ['m/static/src/js/missing.js']}}"
    )
    (root / "odoo-doctor.toml").write_text(_BASE_CONFIG + extra_config)
    return root / "addons"


def _diag(tier: str, confidence: str) -> Diagnostic:
    return Diagnostic(
        "m", "f", 1, 0, "r", "Security", "error", tier, "native", confidence,
        "t", "m", "h", "17.0",
    )  # fmt: skip


def test_default_policy_values():
    ci = _build_config({}).surfaces["ci_failure"]
    assert ci.tiers == ["P0", "P1"] and ci.min_confidence == "high"
    assert _build_config({}).surfaces["pr_comment"].tiers == []


def test_policy_filters_tier_and_confidence():
    ci = _build_config({}).surfaces["ci_failure"]
    kept = filter_for_surface(
        [_diag("P0", "high"), _diag("P1", "high"), _diag("P2", "high"),
         _diag("P1", "low"), _diag("P3", "high")],
        ci,
    )  # fmt: skip
    assert [(d.tier, d.confidence) for d in kept] == [("P0", "high"), ("P1", "high")]


def test_p2_error_does_not_fail_build_by_default(tmp_path: Path):
    addons = _p2_error_addon(tmp_path)
    result = runner.invoke(app, ["scan", str(addons), "--fail-on", "error"])
    assert (
        "asset-bundle-missing" in result.output
        or "Asset file not found" in result.output
    )
    assert result.exit_code == 0


def test_tiers_override_restores_strict_behavior(tmp_path: Path):
    addons = _p2_error_addon(
        tmp_path, '[surfaces.ci_failure]\ntiers = ["P0", "P1", "P2", "P3"]\n'
    )
    result = runner.invoke(app, ["scan", str(addons), "--fail-on", "error"])
    assert result.exit_code == 1


def test_empty_tiers_means_every_tier(tmp_path: Path):
    addons = _p2_error_addon(tmp_path, "[surfaces.ci_failure]\ntiers = []\n")
    result = runner.invoke(app, ["scan", str(addons), "--fail-on", "error"])
    assert result.exit_code == 1
