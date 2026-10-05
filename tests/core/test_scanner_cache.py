"""Second scan of an unchanged repo reuses the cached result."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.core.cache import ScanCache
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.scanner import _score_per_module, collect_scores


def _addon(tmp_path: Path) -> Path:
    mod = tmp_path / "my_addon"
    mod.mkdir()
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], 'data': []}"
    )
    return tmp_path


def test_cache_populated_on_first_scan_and_hit_on_second(tmp_path: Path):
    root = _addon(tmp_path)
    cfg = OdooDoctorConfig(odoo_version="17.0")
    cache = ScanCache(tmp_path / ".odoo_doctor_cache")

    diags1, _scores1 = collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    # The single cache entry is now populated.
    assert cache._fp is not None

    diags2, _scores2 = collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    assert sorted(d.rule for d in diags1) == sorted(d.rule for d in diags2)


def test_cache_invalidated_when_a_file_changes(tmp_path: Path):
    root = _addon(tmp_path)
    cfg = OdooDoctorConfig(odoo_version="17.0")
    cache = ScanCache(tmp_path / ".odoo_doctor_cache")

    collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    fp_before = cache._fp

    # Add a license so the missing-required-fields finding disappears.
    (root / "my_addon" / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], "
        "'data': [], 'installable': True, 'license': 'LGPL-3'}"
    )
    diags2, _ = collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    assert cache._fp != fp_before
    assert not any(d.rule == "manifest-missing-required-fields" for d in diags2)


_RULE = "raw-sql-string-interpolation"


def _cfg() -> OdooDoctorConfig:
    return OdooDoctorConfig(
        odoo_version="17.0",
        adapters={"ruff": False, "pylint_odoo": False, "oca": False},
    )


def _addon_with_suppression(tmp_path: Path) -> Path:
    """One inline-suppressed and one surfaced raw-sql finding."""
    mod = tmp_path / "mod"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    (mod / "models" / "m.py").write_text(
        "from odoo import models\n\n"
        "class M(models.Model):\n"
        "    _name = 'mod.m'\n"
        "    _description = 'M'\n\n"
        "    def run(self, name):\n"
        "        # odoo-doctor: disable=raw-sql-string-interpolation\n"
        "        self.env.cr.execute(f\"SELECT 1 FROM t WHERE n = '{name}'\")\n"
        "        self.env.cr.execute(f\"SELECT 2 FROM t WHERE n = '{name}'\")\n"
    )
    return tmp_path


_EXPECTED = {"surfaced": 1, "inline": 1, "ignore_rule": 0, "severity_off": 0}


def test_live_scan_records_suppression_stats(tmp_path: Path):
    root = _addon_with_suppression(tmp_path)
    _, scores = collect_scores(
        addon_paths=[root], cfg=_cfg(), version="17.0", config_root=root
    )
    assert scores["mod"].suppression_stats[_RULE] == _EXPECTED


def test_cache_hit_returns_the_same_stats_as_the_live_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _addon_with_suppression(tmp_path)
    cache = ScanCache(tmp_path / ".odoo_doctor_cache")
    _, live = collect_scores(
        addon_paths=[root], cfg=_cfg(), version="17.0", config_root=root, cache=cache
    )

    def boom(*args, **kwargs):
        raise AssertionError("graph rebuilt: expected a cache hit")

    monkeypatch.setattr("odoo_doctor.core.scanner.build_project_graph", boom)
    _, hit = collect_scores(
        addon_paths=[root], cfg=_cfg(), version="17.0", config_root=root, cache=cache
    )
    assert hit["mod"].suppression_stats == live["mod"].suppression_stats
    assert hit["mod"].suppression_stats[_RULE] == _EXPECTED


def test_diff_scan_collects_no_stats(tmp_path: Path):
    root = _addon_with_suppression(tmp_path)
    changed = {str((root / "mod" / "models" / "m.py").resolve())}
    _, scores = collect_scores(
        addon_paths=[root],
        cfg=_cfg(),
        version="17.0",
        changed_files=changed,
        config_root=root,
    )
    assert scores["mod"].suppression_stats == {}


def test_score_per_module_keeps_modules_that_only_have_stats():
    stats = {
        "ghost": {
            "r": {"surfaced": 0, "inline": 3, "ignore_rule": 0, "severity_off": 0}
        }
    }
    scores = _score_per_module([], _cfg(), "17.0", stats=stats, extra_modules=stats)
    assert scores["ghost"].suppression_stats == stats["ghost"]
    # without extra_modules the module set is unchanged (baseline re-scoring relies on it)
    assert _score_per_module([], _cfg(), "17.0", stats=stats) == {}
