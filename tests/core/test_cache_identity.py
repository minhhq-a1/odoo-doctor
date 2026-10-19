"""What the scan cache key covers, and what a hit reproduces."""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import odoo_doctor.cli.app  # noqa: F401  (registers the built-in rules)
from odoo_doctor.core import scanner
from odoo_doctor.core.cache import ScanCache
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scanner import _score_per_module, collect_scores
from odoo_doctor.rules.registry import RuleRegistry, rule

_NO_ADAPTERS = {"ruff": False, "pylint_odoo": False, "oca": False}


def _addon(root: Path, version: str = "17.0.1.0.0") -> Path:
    mod = root / "mod"
    mod.mkdir()
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        f"{{'name': 'mod', 'version': '{version}', 'depends': ['base'], "
        "'data': [], 'license': 'LGPL-3'}"
    )
    (mod / "a.py").write_text("x = 1\n")
    return root


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return _addon(root)


def _finding(module: str = "mod") -> Diagnostic:
    return Diagnostic(
        module=module,
        file_path="/x/a.py",
        line=1,
        column=0,
        rule="plugin-rule",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="m",
        help="h",
        odoo_version="17.0",
    )


def _run(root: Path, cache: ScanCache, cfg: OdooDoctorConfig | None = None, **kw):
    cfg = cfg or OdooDoctorConfig(adapters=dict(_NO_ADAPTERS))
    return collect_scores(
        [root], cfg, kw.pop("version", "unknown"), config_root=root, cache=cache, **kw
    )


# --- (1) a hit reproduces the version the live scan detected ----------------------


@pytest.fixture
def gated_registry(monkeypatch):
    """A registry whose Security category exists only on Odoo 17: the in-scope
    categories then depend on the version the scan runs as."""
    reg = RuleRegistry()

    @rule(
        "only-17",
        "Security",
        "P1",
        "error",
        "high",
        False,
        registry=reg,
        requires_capabilities={"odoo:17"},
    )
    def _only_17(file, module, version):
        return []

    @rule("always", "Correctness", "P1", "error", "high", False, registry=reg)
    def _always(file, module, version):
        return []

    monkeypatch.setattr(scanner, "default_registry", reg)
    return reg


def test_hit_scores_with_the_version_the_live_scan_detected(
    tmp_path: Path, gated_registry
):
    root = _addon(tmp_path)  # manifest says 17.0, config says nothing
    cache = ScanCache(tmp_path / ".cache")
    _, live = _run(root, cache)
    _, hit = _run(root, cache)
    assert live["mod"].in_scope_categories == ["Security", "Correctness"]
    assert hit["mod"].in_scope_categories == live["mod"].in_scope_categories
    assert hit["mod"] == live["mod"]


def test_version_survives_the_disk_round_trip(tmp_path: Path, gated_registry):
    root = _addon(tmp_path)
    cache = ScanCache(tmp_path / ".cache")
    _run(root, cache)
    cache.save()
    reloaded = ScanCache(tmp_path / ".cache")
    reloaded.load()
    _, hit = _run(root, reloaded)
    assert hit["mod"].in_scope_categories == ["Security", "Correctness"]


def test_hit_keeps_the_module_order_of_the_live_scan():
    diags = [_finding("zeta")]
    order = ["zeta", "alpha", "mid", "beta", "omega", "gamma"]
    scores = _score_per_module(diags, OdooDoctorConfig(), "17.0", extra_modules=order)
    assert list(scores) == order


# --- config repr is stable across processes ----------------------------------------


def test_config_repr_does_not_depend_on_the_hash_seed():
    code = (
        "from odoo_doctor.core.config import OdooDoctorConfig;"
        "from odoo_doctor.core.scanner import _config_repr;"
        "print(_config_repr(OdooDoctorConfig("
        "explicit_adapters={'ruff', 'pylint_odoo', 'oca', 'x', 'y'})))"
    )
    outs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2", "3")
    }
    assert len(outs) == 1


# --- (2) plugin rules ---------------------------------------------------------------


def _load_plugin(path: Path, body: str, registry: RuleRegistry):
    """Write and import a plugin module that registers one rule, as an entry point would."""
    path.write_text(
        "from odoo_doctor.rules.registry import rule\n"
        "from odoo_doctor.core.diagnostics import Diagnostic\n"
        f"def make(registry):\n"
        "    @rule('plugin-rule', 'Security', 'P0', 'error', 'high', False,\n"
        "          registry=registry)\n"
        "    def check(file, module, version):\n"
        f"        {body}\n"
        "    return check\n"
    )
    spec = importlib.util.spec_from_file_location("k3_fake_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["k3_fake_plugin"] = mod
    spec.loader.exec_module(mod)
    mod.make(registry)


def test_a_plugin_rule_that_changes_invalidates_the_cache(tmp_path: Path, monkeypatch):
    reg = RuleRegistry()
    monkeypatch.setattr(scanner, "default_registry", reg)
    monkeypatch.delitem(sys.modules, "k3_fake_plugin", raising=False)
    root = _project(tmp_path)
    plugin = tmp_path / "k3_fake_plugin.py"
    cache = ScanCache(tmp_path / ".cache")

    _load_plugin(plugin, "return []", reg)
    first, _ = _run(root, cache)
    assert first == []

    # same plugin, same name, same min_version, new behaviour
    reg.unregister("plugin-rule")
    body = (
        "from odoo_doctor.core.diagnostics import Diagnostic as D; "
        "return [D(module, str(file), 1, 0, 'plugin-rule', 'Security', 'error', "
        "'P0', 'native', 'high', 't', 'm', 'h', version)] "
        "if file.name == 'a.py' else []"
    )
    _load_plugin(plugin, body, reg)
    second, _ = _run(root, cache)
    assert [d.rule for d in second] == ["plugin-rule"]
    sys.modules.pop("k3_fake_plugin", None)


# --- (3) linter versions and flags ---------------------------------------------------


def _fake_ruff(directory: Path, version: str) -> Path:
    directory.mkdir()
    exe = directory / "ruff"
    exe.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "x" >> "$(dirname "$0")/calls"; '
        f'echo "ruff {version}"; else echo "[]"; fi\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return directory


@pytest.mark.skipif(os.name == "nt", reason="shell script stand-in for ruff")
def test_a_new_ruff_version_invalidates_the_cache(tmp_path: Path, monkeypatch):
    from odoo_doctor.core import cache as cache_mod

    monkeypatch.setattr(cache_mod, "_tool_versions", {}, raising=False)
    old = _fake_ruff(tmp_path / "bin1", "0.16.1")
    new = _fake_ruff(tmp_path / "bin2", "0.16.2")
    root = _project(tmp_path)
    cfg = OdooDoctorConfig(adapters={"ruff": True, "pylint_odoo": False, "oca": False})
    cache = ScanCache(tmp_path / ".cache")

    monkeypatch.setenv("PATH", f"{old}{os.pathsep}{os.environ['PATH']}")
    _run(root, cache, cfg)
    fp_old = cache._fp
    _run(root, cache, cfg)
    assert cache._fp == fp_old  # same tool: a hit
    assert (old / "calls").read_text().count("x") == 1  # --version ran once

    monkeypatch.setenv("PATH", f"{new}{os.pathsep}{os.environ['PATH']}")
    _run(root, cache, cfg)
    assert cache._fp != fp_old


def test_ruff_enabled_flag_is_part_of_the_key(tmp_path: Path):
    root = _addon(tmp_path)
    cache = ScanCache(tmp_path / ".cache")
    on = OdooDoctorConfig(adapters={"ruff": True, "pylint_odoo": False, "oca": False})
    _run(root, cache, on)
    fp_on = cache._fp
    _run(root, cache, OdooDoctorConfig(adapters=dict(_NO_ADAPTERS)))
    assert cache._fp != fp_on


def test_a_missing_linter_has_a_fixed_marker(monkeypatch):
    from odoo_doctor.core.cache import adapter_identities

    monkeypatch.setenv("PATH", "")
    assert adapter_identities({"ruff": True, "pylint_odoo": False}) == (
        "adapter=pylint_odoo:off",
        "adapter=ruff:unavailable",
    )


@pytest.mark.skipif(os.name == "nt", reason="shell script stand-ins")
def test_pylint_odoo_version_comes_from_the_interpreter_behind_pylint(tmp_path: Path):
    from odoo_doctor.core.cache import _pylint_odoo_version

    interp = tmp_path / "fakepython"
    interp.write_text("#!/bin/sh\necho 9.9.9\n")
    interp.chmod(0o755)
    pylint = tmp_path / "pylint"
    pylint.write_text(f"#!{interp}\n")
    assert _pylint_odoo_version(str(pylint), str(tmp_path)) == "9.9.9"
    pylint.write_text("not a script\n")
    assert _pylint_odoo_version(str(pylint), str(tmp_path)) == "unknown"
