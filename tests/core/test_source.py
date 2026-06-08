# tests/core/test_source.py
"""Tests for the crash-safe source reader."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.source import read_source


def test_read_source_reads_utf8(tmp_path: Path):
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n")
    assert read_source(f) == "x = 1\n"


def test_read_source_replaces_non_utf8_bytes(tmp_path: Path):
    f = tmp_path / "bad.py"
    # 0xE9 is 'é' in latin-1 and an invalid UTF-8 start byte
    f.write_bytes(b"x = '\xe9'\n")
    out = read_source(f)
    assert out is not None
    assert "\ufffd" in out  # decoded with errors="replace", did not raise


def test_read_source_returns_none_for_missing_file(tmp_path: Path):
    assert read_source(tmp_path / "does_not_exist.py") is None


def test_read_source_returns_none_for_directory(tmp_path: Path):
    # Reading a directory raises OSError → None, never propagates
    assert read_source(tmp_path) is None
