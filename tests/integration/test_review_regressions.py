"""Regressions for findings lost or changed by scan orchestration."""

import json
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app
from odoo_doctor.core.cache import ScanCache
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scanner import collect_scores
from odoo_doctor.rules.registry import default_registry, rule

runner = CliRunner()


def addon(root, name="m", version="19.0", **extra):
    mod = root / name
    mod.mkdir(parents=True)
    manifest = {
        "name": name,
        "version": version + ".1.0.0",
        "depends": ["base"],
        "data": [],
        "license": "LGPL-3",
    }
    manifest.update(extra)
    (mod / "__manifest__.py").write_text(repr(manifest))
    (mod / "__init__.py").touch()
    return mod


def no_adapters(root):
    (root / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )


def scan(root, *args):
    result = runner.invoke(app, ["scan", str(root), "--json", *map(str, args)])
    assert result.exit_code in (0, 1, 2), (result.output, result.exception)
    return result, json.loads(result.stdout)


def findings(report, name=None):
    return [
        d
        for m in report["modules"].values()
        for d in m["diagnostics"]
        if name is None or d["rule"] == name
    ]


def test_ci_default_is_same_with_absent_and_empty_config(tmp_path):
    addon(tmp_path, assets={"web.assets_backend": ["m/static/missing.js"]})
    absent, report = scan(tmp_path, "--fail-on", "error")
    assert findings(report, "asset-bundle-missing")
    (tmp_path / "odoo-doctor.toml").touch()
    empty, _ = scan(tmp_path, "--fail-on", "error")
    assert empty.exit_code == 0
    assert absent.exit_code == empty.exit_code, (
        f"absent_config_exit={absent.exit_code}, empty_config_exit={empty.exit_code}"
    )


def test_newer_addon_findings_survive_older_sibling(tmp_path):
    addon(tmp_path, "a_old", "17.0")
    new = addon(tmp_path, "b_new", "19.0", data=["action.xml"])
    (new / "action.xml").write_text(
        '<odoo>\n<record id="action" model="ir.actions.act_window">\n'
        '<field name="name">Test</field>\n'
        '<field name="res_model">res.partner</field>\n'
        '<field name="view_mode">tree,form</field>\n</record>\n</odoo>\n'
    )
    no_adapters(tmp_path)
    _, alone = scan(new)
    _, together = scan(tmp_path)
    alone_count = len(findings(alone, "view-tree-removed"))
    combined_count = len(findings(together, "view-tree-removed"))
    assert alone_count == 1
    assert combined_count == alone_count, (
        f"new_addon_alone={alone_count}, with_17_sibling={combined_count}"
    )


def test_dedup_keeps_distinct_missing_manifest_fields(tmp_path):
    mod = addon(tmp_path)
    (mod / "__manifest__.py").write_text("{'version': '19.0.1.0.0', 'depends': []}")
    no_adapters(tmp_path)
    _, report = scan(tmp_path)
    actual = [d["title"] for d in findings(report, "manifest-missing-required-fields")]
    assert len(actual) == 3, actual  # distinct missing name, data and license


def test_dedup_keeps_distinct_missing_dependencies(tmp_path):
    consumer = addon(tmp_path, "consumer", depends=[])
    (consumer / "models.py").write_text(
        "from odoo import models\n"
        "class First(models.Model):\n    _inherit = 'first.model'\n"
        "class Second(models.Model):\n    _inherit = 'second.model'\n"
    )
    for name in ("first", "second"):
        provider = addon(tmp_path, name, depends=[])
        (provider / "models.py").write_text(
            "from odoo import models\n"
            f"class Provider(models.Model):\n    _name = '{name}.model'\n"
        )
    no_adapters(tmp_path)
    _, report = scan(tmp_path)
    actual = findings(report, "manifest-missing-dependency")
    assert all(d["tier"] == "P1" and d["confidence"] == "high" for d in actual)
    assert len(actual) == 2, [d["title"] for d in actual]


def test_baseline_survives_a_different_checkout_directory(tmp_path):
    original = tmp_path / "checkout_one"
    copied = tmp_path / "checkout_two"
    mod = addon(original)
    (mod / "risk.py").write_text("def run(value):\n    return eval(value)\n")
    no_adapters(original)
    baseline = tmp_path / "baseline.json"
    write = runner.invoke(
        app, ["scan", str(original), "--write-baseline", str(baseline)]
    )
    assert write.exit_code == 0, write.output
    _, same = scan(original, "--baseline", baseline)
    assert not findings(same, "eval-usage")
    shutil.copytree(original, copied)
    _, other = scan(copied, "--baseline", baseline)
    assert not findings(other, "eval-usage"), (
        "unchanged debt resurfaces after checkout moves"
    )


@pytest.mark.skipif(shutil.which("ruff") is None, reason="Ruff not installed")
@pytest.mark.parametrize("config_kind", ["local", "ancestor", "extended"])
def test_cache_invalidates_when_ruff_configuration_changes(tmp_path, config_kind):
    project = tmp_path / "project"
    project.mkdir()
    root = project / "addons"
    root.mkdir()
    if config_kind == "local":
        ruff_config = root / "pyproject.toml"
        table = "tool.ruff.lint"
    elif config_kind == "ancestor":
        ruff_config = project / "pyproject.toml"
        table = "tool.ruff.lint"
    else:
        ruff_config = tmp_path / "shared.toml"
        (root / "ruff.toml").write_text('extend = "../../shared.toml"\n')
        table = "lint"
    mod = addon(root)
    (mod / "unused.py").write_text("def f():\n    unused_variable = 1\n")
    ruff_config.write_text(f'[{table}]\nselect = ["F841"]\n')
    cfg = OdooDoctorConfig(adapters={"ruff": True, "pylint_odoo": False})
    cache = ScanCache(tmp_path / ".cache")
    first, _ = collect_scores([root], cfg, "19.0", cache=cache, config_root=root)
    assert len([d for d in first if d.rule == "F841"]) == 1
    # the scanned repo's ruff configuration never steers the run (ruff runs --isolated, see
    # the 0.11.1 security notes), so the finding stays; the key still moves, and a hit must
    # equal a fresh scan
    ruff_config.write_text(f'[{table}]\nselect = ["F841"]\nignore = ["F841"]\n')
    cached, _ = collect_scores([root], cfg, "19.0", cache=cache, config_root=root)
    fresh, _ = collect_scores([root], cfg, "19.0", config_root=root)
    cached_count = len([d for d in cached if d.rule == "F841"])
    fresh_count = len([d for d in fresh if d.rule == "F841"])
    assert fresh_count == 1
    assert cached_count == fresh_count, f"cached={cached_count}, fresh={fresh_count}"


@pytest.mark.skipif(
    shutil.which("ruff") is None or shutil.which("git") is None,
    reason="Ruff and git required",
)
def test_cache_invalidates_when_ruff_gitignore_changes(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    mod = addon(tmp_path)
    (mod / "unused.py").write_text("def f():\n    unused_variable = 1\n")
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["F841"]\n')
    cfg = OdooDoctorConfig(adapters={"ruff": True, "pylint_odoo": False})
    cache = ScanCache(tmp_path / ".cache")
    first, _ = collect_scores([tmp_path], cfg, "19.0", cache=cache)
    assert any(d.rule == "F841" for d in first)
    (tmp_path / ".gitignore").write_text("m/unused.py\n")
    cached, _ = collect_scores([tmp_path], cfg, "19.0", cache=cache)
    fresh, _ = collect_scores([tmp_path], cfg, "19.0")
    assert not any(d.rule == "F841" for d in fresh)
    assert cached == fresh


@pytest.mark.skipif(shutil.which("ruff") is None, reason="Ruff not installed")
def test_cache_invalidates_when_ruff_stub_changes(tmp_path):
    mod = addon(tmp_path)
    stub = mod / "stub.pyi"
    stub.write_text("import os\n")
    cfg = OdooDoctorConfig(adapters={"ruff": True, "pylint_odoo": False})
    cache = ScanCache(tmp_path / ".cache")
    first, _ = collect_scores([tmp_path], cfg, "19.0", cache=cache)
    assert any(d.rule == "F401" for d in first)
    stub.write_text("")
    cached, _ = collect_scores([tmp_path], cfg, "19.0", cache=cache)
    fresh, _ = collect_scores([tmp_path], cfg, "19.0")
    assert not any(d.rule == "F401" for d in fresh)
    assert cached == fresh


@pytest.mark.parametrize("diff", [False, True])
def test_context_plugin_can_yield_diagnostics(tmp_path, diff):
    addon(tmp_path)
    name = "review-generator-context"

    @rule(
        name=name,
        category="Security",
        tier="P1",
        severity="error",
        default_confidence="high",
        needs_context=True,
    )
    def check(ctx):
        yield Diagnostic(
            ctx.name,
            str(ctx.path / "__manifest__.py"),
            1,
            0,
            name,
            "Security",
            "error",
            "P1",
            "native",
            "high",
            "test finding",
            "test message",
            "help",
            ctx.odoo_version,
        )

    try:
        cfg = OdooDoctorConfig(adapters={"ruff": False, "pylint_odoo": False})
        diags, _ = collect_scores(
            [tmp_path],
            cfg,
            "19.0",
            config_root=tmp_path,
            changed_files={str(tmp_path / "m" / "__init__.py")} if diff else None,
        )
        assert len([d for d in diags if d.rule == name]) == 1
    finally:
        default_registry.unregister(name)


def test_cached_module_scope_matches_live_scope(tmp_path, monkeypatch):
    """Even a module with no diagnostics retains its own version-dependent scope."""
    from dataclasses import asdict

    from odoo_doctor.rules.registry import RuleRegistry

    registry = RuleRegistry()

    @rule(
        name="versioned-security",
        category="Security",
        tier="P1",
        severity="error",
        default_confidence="high",
        needs_context=True,
        min_version="19.0",
        registry=registry,
    )
    def check(ctx):
        return []

    monkeypatch.setattr("odoo_doctor.core.scanner.default_registry", registry)
    addon(tmp_path, "a_old", "14.0")
    addon(tmp_path, "b_new", "19.0")
    cfg = OdooDoctorConfig(adapters={"ruff": False, "pylint_odoo": False})
    cache = ScanCache(tmp_path / ".cache")
    _, live = collect_scores([tmp_path], cfg, "unknown", cache=cache)
    cache.save()
    reloaded = ScanCache(tmp_path / ".cache")
    reloaded.load()
    _, cached = collect_scores([tmp_path], cfg, "unknown", cache=reloaded)
    assert live["a_old"].in_scope_categories != live["b_new"].in_scope_categories
    assert {n: asdict(s) for n, s in cached.items()} == {
        n: asdict(s) for n, s in live.items()
    }
