"""deprecated-orm-api-usage: still-defined ORM methods that Odoo 18/19 deprecate."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.deprecated_orm_api_usage import (
    check_deprecated_orm_api_usage,
)


def _check(tmp_path: Path, source: str, version: str = "19.0", where="models/m.py"):
    path = tmp_path / "mod" / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return check_deprecated_orm_api_usage(path, "mod", version)


MODEL = "from odoo import models\n\nclass A(models.Model):\n    _name = 'x.a'\n"


def test_read_group_call_is_flagged_high_on_a_record(tmp_path: Path):
    diags = _check(
        tmp_path,
        MODEL + "    def stats(self):\n"
        "        return self.env['x.b'].read_group([], ['qty:sum'], ['p'])\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence, d.severity) == (
        "deprecated-orm-api-usage",
        "P2",
        "Upgrade Safety",
        "high",
        "warning",
    )
    assert d.line == 6
    assert "_read_group" in d.help


def test_read_group_override_is_flagged_as_not_called(tmp_path: Path):
    diags = _check(
        tmp_path,
        MODEL + "    def read_group(self, domain, fields, groupby, **kw):\n"
        "        return super().read_group(domain, fields, groupby, **kw)\n",
    )
    assert len(diags) == 1  # the override; the super() call is not reported twice
    assert "Override" in diags[0].title
    assert diags[0].line == 5
    assert "formatted_read_group" in diags[0].message


def test_call_on_an_unrelated_object_is_medium(tmp_path: Path):
    diags = _check(
        tmp_path, MODEL + "    def f(self, rec):\n        rec.toggle_active()\n"
    )
    assert [d.confidence for d in diags] == ["medium"]


@pytest.mark.parametrize(
    "call,version,expected",
    [
        ("self.check_access_rights('read')", "18.0", 1),
        ("self.check_access_rights('read')", "17.0", 0),
        ("self.check_access_rule('read')", "19.0", 1),
        ("self._check_recursion()", "18.0", 1),
        ("self._check_recursion()", "17.0", 0),
        ("self.read_group([], [], [])", "18.0", 0),
        ("self.toggle_active()", "18.0", 0),
        ("self.toggle_active()", "19.0", 1),
        ("self.check_field_access_rights('read', None)", "19.0", 1),
        ("self._read_group([], [])", "19.0", 0),
        ("self.check_access('read')", "19.0", 0),
    ],
)
def test_each_api_is_gated_on_the_version_that_deprecates_it(
    tmp_path: Path, call: str, version: str, expected: int
):
    diags = _check(tmp_path, MODEL + f"    def f(self):\n        {call}\n", version)
    assert len(diags) == expected


def test_other_overrides_are_not_flagged_only_their_calls(tmp_path: Path):
    diags = _check(
        tmp_path,
        MODEL
        + "    def toggle_active(self):\n        return super().toggle_active()\n",
    )
    assert diags == []


def test_tests_and_migrations_are_skipped(tmp_path: Path):
    src = MODEL + "    def f(self):\n        self.read_group([], [], [])\n"
    assert _check(tmp_path, src, where="tests/test_a.py") == []
    assert _check(tmp_path, src, where="migrations/19.0.1.0/post.py") == []
