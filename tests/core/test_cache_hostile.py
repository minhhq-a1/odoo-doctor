"""A hostile `.odoo_doctor_cache` in the scanned repo cannot hang a scan or redirect a write."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from odoo_doctor.core.cache import CACHE_VERSION, ScanCache


def _addon(root: Path) -> None:
    mod = root / "mod"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text("{'name': 'M', 'version': '17.0.1.0.0'}")
    (mod / "__init__.py").write_text("")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no os.mkfifo")
def test_fifo_as_cache_file_does_not_hang_a_cached_scan(tmp_path: Path):
    _addon(tmp_path)
    cache_dir = tmp_path / ".odoo_doctor_cache"
    cache_dir.mkdir()
    os.mkfifo(cache_dir / "scan_cache.json")
    code = "from odoo_doctor.cli.app import app; app()"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, "scan", str(tmp_path), "--cache", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("scan --cache blocked on a FIFO cache file")
    assert proc.returncode in (0, 1), proc.stderr


def _store(cache: ScanCache) -> None:
    cache.store("fp", [], {}, {}, "17.0")
    cache.save()


def test_save_does_not_follow_a_symlinked_cache_file(tmp_path: Path):
    root = tmp_path / "repo"
    cache_dir = root / ".odoo_doctor_cache"
    cache_dir.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    try:
        (cache_dir / "scan_cache.json").symlink_to(victim)
    except OSError:
        pytest.skip("cannot create symlinks")
    _store(ScanCache(cache_dir))
    assert victim.read_text() == "precious"


def test_save_does_not_follow_a_symlinked_cache_dir(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        (root / ".odoo_doctor_cache").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks")
    _store(ScanCache(root / ".odoo_doctor_cache"))
    assert list(elsewhere.iterdir()) == []


def test_load_ignores_a_symlinked_cache_file_leaving_the_repo(tmp_path: Path):
    root = tmp_path / "repo"
    cache_dir = root / ".odoo_doctor_cache"
    cache_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps({"cache_version": CACHE_VERSION, "fp": "x", "diagnostics": []})
    )
    try:
        (cache_dir / "scan_cache.json").symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlinks")
    cache = ScanCache(cache_dir)
    cache.load()
    assert cache.lookup("x") is None


def test_normal_round_trip_still_works(tmp_path: Path):
    cache_dir = tmp_path / "repo" / ".odoo_doctor_cache"
    _store(ScanCache(cache_dir))
    again = ScanCache(cache_dir)
    again.load()
    assert again.lookup("fp") == []
