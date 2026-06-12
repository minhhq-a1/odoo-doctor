"""Second scan of an unchanged repo reuses the cached result."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.cache import ScanCache
from odoo_doctor.core.scanner import collect_scores


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

    diags1, scores1 = collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    # The single cache entry is now populated.
    assert cache._fp is not None  # noqa: SLF001 - white-box check is fine in tests

    diags2, scores2 = collect_scores(
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
    fp_before = cache._fp  # noqa: SLF001

    # Add a license so the missing-required-fields finding disappears.
    (root / "my_addon" / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], "
        "'data': [], 'installable': True, 'license': 'LGPL-3'}"
    )
    diags2, _ = collect_scores(
        addon_paths=[root], cfg=cfg, version="17.0", config_root=root, cache=cache
    )
    assert cache._fp != fp_before  # noqa: SLF001 - fingerprint changed -> miss
    assert not any(d.rule == "manifest-missing-required-fields" for d in diags2)
