# tests/rules/test_search_in_loop_encoding.py
"""search-in-loop must not crash on a non-UTF-8 source file."""

from __future__ import annotations

from odoo_doctor.rules.performance.search_in_loop import check_search_in_loop


def test_search_in_loop_tolerates_non_utf8(tmp_path):
    f = tmp_path / "bad.py"
    f.write_bytes(b"x = '\xe9'\n")
    assert check_search_in_loop(f, "m", "17.0") == []
