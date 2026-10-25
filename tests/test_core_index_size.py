"""The packaged core index stays within the wheel budget and loads (spec 0.13, D4)."""

from __future__ import annotations

from odoo_doctor.graph import core_index

BUDGET_BYTES = 3 * 1024 * 1024


def test_packaged_index_within_budget_and_loadable():
    files = sorted(core_index._DATA_DIR.glob("*.json.gz"))
    assert sum(f.stat().st_size for f in files) <= BUDGET_BYTES
    for f in files:
        assert core_index.get_core_index(f.name.removesuffix(".json.gz")) is not None
