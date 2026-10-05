"""Project-level fingerprinting and cache round-trip."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.cache import project_fingerprint, ScanCache


def _addon(tmp_path: Path) -> Path:
    mod = tmp_path / "m"
    mod.mkdir()
    (mod / "__manifest__.py").write_text("{'name': 'M'}")
    (mod / "a.py").write_text("x = 1\n")
    return tmp_path


def test_fingerprint_changes_when_a_file_changes(tmp_path: Path):
    root = _addon(tmp_path)
    fp1 = project_fingerprint([root], config_repr="c", version="17.0", ruleset=("r",))
    (root / "m" / "a.py").write_text("x = 2\n")
    fp2 = project_fingerprint([root], config_repr="c", version="17.0", ruleset=("r",))
    assert fp1 != fp2


def test_fingerprint_changes_when_config_changes(tmp_path: Path):
    root = _addon(tmp_path)
    fp1 = project_fingerprint([root], config_repr="c1", version="17.0", ruleset=("r",))
    fp2 = project_fingerprint([root], config_repr="c2", version="17.0", ruleset=("r",))
    assert fp1 != fp2


def test_fingerprint_changes_when_ruleset_changes(tmp_path: Path):
    root = _addon(tmp_path)
    fp1 = project_fingerprint([root], config_repr="c", version="17.0", ruleset=("a",))
    fp2 = project_fingerprint(
        [root], config_repr="c", version="17.0", ruleset=("a", "b")
    )
    assert fp1 != fp2


def test_fingerprint_stable_when_unchanged(tmp_path: Path):
    root = _addon(tmp_path)
    a = project_fingerprint([root], config_repr="c", version="17.0", ruleset=("r",))
    b = project_fingerprint([root], config_repr="c", version="17.0", ruleset=("r",))
    assert a == b


def test_cache_round_trip(tmp_path: Path):
    cache = ScanCache(tmp_path / ".odoo_doctor_cache")
    cache.store("fp123", [{"rule": "x"}])
    cache.save()

    reloaded = ScanCache(tmp_path / ".odoo_doctor_cache")
    reloaded.load()
    assert reloaded.lookup("fp123") == [{"rule": "x"}]
    assert reloaded.lookup("other-fp") is None


def test_cache_version_mismatch_misses(tmp_path: Path):
    import odoo_doctor.core.cache as cache_mod

    cache = ScanCache(tmp_path / ".odoo_doctor_cache")
    cache.store("fp123", [{"rule": "x"}])
    cache.save()

    # Simulate a schema bump: an old on-disk cache must not be trusted.
    orig = cache_mod.CACHE_VERSION
    try:
        cache_mod.CACHE_VERSION = orig + 1
        fresh = ScanCache(tmp_path / ".odoo_doctor_cache")
        fresh.load()
        assert fresh.lookup("fp123") is None
    finally:
        cache_mod.CACHE_VERSION = orig


def test_cache_round_trip_keeps_suppression_stats(tmp_path: Path):
    stats = {
        "m": {"r": {"surfaced": 1, "inline": 2, "ignore_rule": 0, "severity_off": 0}}
    }
    cache = ScanCache(tmp_path / ".odoo_doctor_cache")
    cache.store("fp123", [], stats)
    cache.save()

    reloaded = ScanCache(tmp_path / ".odoo_doctor_cache")
    reloaded.load()
    assert reloaded.lookup_stats("fp123") == stats


def test_version_1_cache_file_misses_cleanly(tmp_path: Path):
    cache_dir = tmp_path / ".odoo_doctor_cache"
    cache_dir.mkdir()
    (cache_dir / "scan_cache.json").write_text(
        '{"cache_version": 1, "fp": "fp123", "diagnostics": []}', encoding="utf-8"
    )
    cache = ScanCache(cache_dir)
    cache.load()
    assert cache.lookup("fp123") is None
