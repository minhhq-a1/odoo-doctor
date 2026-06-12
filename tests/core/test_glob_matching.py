"""_matches_any_glob must do real glob matching, not substring matching."""

from __future__ import annotations

from odoo_doctor.core.pipeline import _matches_any_glob


def test_double_star_matches_real_directory_segment():
    assert _matches_any_glob("my_addon/migrations/17.0/pre.py", ["**/migrations/**"])


def test_double_star_does_not_match_substring_dir():
    # 'migrations_backup' must NOT be caught by '**/migrations/**'
    assert not _matches_any_glob(
        "my_addon/migrations_backup/file.py", ["**/migrations/**"]
    )


def test_double_star_does_not_match_substring_in_filename():
    assert not _matches_any_glob(
        "my_addon/models/migrations_helper.py", ["**/migrations/**"]
    )


def test_plain_glob_still_matches():
    assert _matches_any_glob("a/b/test_x.py", ["**/test_*.py"])
    assert _matches_any_glob("models.py", ["*.py"])


def test_non_match_returns_false():
    assert not _matches_any_glob("a/b/c.py", ["**/migrations/**"])
