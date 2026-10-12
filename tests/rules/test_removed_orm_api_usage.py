"""removed-orm-api-usage: name_get (18), fields_view_get and invalidate_cache (17) are gone."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.removed_orm_api_usage import (
    check_removed_orm_api_usage,
)


def _check(tmp_path: Path, source: str, version: str = "19.0"):
    path = tmp_path / "mod" / "models" / "m.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    return check_removed_orm_api_usage(path, "mod", version)


MODEL = "from odoo import models\n\nclass A(models.Model):\n    _name = 'x.a'\n"


def test_name_get_override_is_flagged_high(tmp_path: Path):
    diags = _check(
        tmp_path,
        MODEL + "    def name_get(self):\n"
        "        return [(r.id, r.name) for r in self]\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "removed-orm-api-usage",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert d.line == 5
    assert "_compute_display_name" in d.help


def test_name_get_is_only_removed_in_18(tmp_path: Path):
    src = MODEL + "    def name_get(self):\n        return []\n"
    assert _check(tmp_path, src, "17.0") == []


@pytest.mark.parametrize(
    "call, replacement",
    [
        ("self.fields_view_get(view_type='form')", "get_view"),
        ("self.env['x.a'].invalidate_cache(['name'])", "invalidate_model"),
        ("self.invalidate_cache()", "invalidate_recordset"),
    ],
)
def test_calls_on_records_are_flagged_high(tmp_path: Path, call, replacement):
    diags = _check(
        tmp_path, MODEL + f"    def go(self):\n        return {call}\n", "17.0"
    )
    assert len(diags) == 1
    assert diags[0].confidence == "high"
    assert replacement in diags[0].help


def test_call_on_an_unknown_object_is_medium(tmp_path: Path):
    diags = _check(
        tmp_path, MODEL + "    def go(self, thing):\n        return thing.name_get()\n"
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_super_call_inside_the_override_is_not_reported_twice(tmp_path: Path):
    diags = _check(
        tmp_path,
        MODEL + "    def name_get(self):\n        return super().name_get()\n",
    )
    assert len(diags) == 1  # the def only


def test_helper_function_with_the_same_name_outside_a_model_is_not_flagged(
    tmp_path: Path,
):
    assert _check(tmp_path, "def name_get(x):\n    return x\n") == []


def test_tests_directory_is_skipped(tmp_path: Path):
    path = tmp_path / "mod" / "tests" / "t.py"
    path.parent.mkdir(parents=True)
    path.write_text(MODEL + "    def go(self):\n        return self.name_get()\n")
    assert check_removed_orm_api_usage(path, "mod", "19.0") == []


def test_migration_scripts_are_skipped(tmp_path: Path):
    path = tmp_path / "mod" / "migrations" / "14.0.1.0.1" / "post-migration.py"
    path.parent.mkdir(parents=True)
    path.write_text("def migrate(cr, version):\n    env = None\n    env.name_get()\n")
    assert check_removed_orm_api_usage(path, "mod", "19.0") == []
