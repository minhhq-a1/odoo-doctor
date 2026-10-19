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


def test_read_source_skips_a_file_over_the_size_cap(tmp_path: Path, monkeypatch):
    from odoo_doctor.core import source

    monkeypatch.setattr(source, "MAX_FILE_BYTES", 10)
    big = tmp_path / "big.py"
    big.write_text("x = 1\n" * 5)
    assert read_source(big) is None
    small = tmp_path / "small.py"
    small.write_text("x = 1")
    assert read_source(small) == "x = 1"


def test_is_scannable_directory_is_silent(tmp_path: Path, capsys):
    from odoo_doctor.core.source import is_scannable

    (tmp_path / "pkg.py").mkdir()
    assert not is_scannable(tmp_path / "pkg.py")
    assert capsys.readouterr().err == ""


def test_is_scannable_rejects_an_absolute_path_outside_the_root(tmp_path: Path):
    from odoo_doctor.core.source import is_scannable

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.xml"
    outside.write_text("<odoo/>")
    assert not is_scannable(
        root / str(outside), root
    )  # pathlib join: the absolute wins
    (root / "in.xml").write_text("<odoo/>")
    assert is_scannable(root / "in.xml", root)
