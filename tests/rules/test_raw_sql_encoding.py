# tests/rules/test_raw_sql_encoding.py
"""raw-sql-string-interpolation must not crash on a non-UTF-8 source file."""

from __future__ import annotations

from odoo_doctor.rules.security.raw_sql_interpolation import check_raw_sql_interpolation


def test_raw_sql_tolerates_non_utf8(tmp_path):
    f = tmp_path / "bad.py"
    f.write_bytes(b"x = '\xe9'\n")
    assert check_raw_sql_interpolation(f, "m", "17.0") == []
