"""sql-constraints-unsupported: Odoo 19 ignores `_sql_constraints` (use models.Constraint)."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.upgrade_safety.sql_constraints_unsupported import (
    check_sql_constraints_unsupported,
)


def _check(tmp_path: Path, source: str, name: str = "m.py"):
    path = tmp_path / "mod" / "models" / name
    path.parent.mkdir(parents=True)
    path.write_text(source)
    return check_sql_constraints_unsupported(path, "mod", "19.0")


def test_model_with_sql_constraints_is_flagged(tmp_path: Path):
    diags = _check(
        tmp_path,
        "from odoo import models\n\n"
        "class A(models.Model):\n"
        "    _name = 'x.a'\n"
        "    _sql_constraints = [\n"
        "        ('name_uniq', 'unique(name)', 'Name must be unique'),\n"
        "        ('qty_pos', 'CHECK(qty > 0)', 'Positive'),\n"
        "    ]\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "sql-constraints-unsupported",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert d.line == 5
    assert "name_uniq" in d.message and "qty_pos" in d.message
    assert "models.Constraint" in d.help


def test_inherit_only_extension_is_flagged(tmp_path: Path):
    diags = _check(
        tmp_path,
        "from odoo import models\n\n"
        "class A(models.Model):\n"
        "    _inherit = 'res.company'\n"
        "    _sql_constraints = [('abbr_uniq', 'unique(abbr)', 'x')]\n",
    )
    assert len(diags) == 1


def test_empty_list_is_not_flagged(tmp_path: Path):
    assert (
        _check(
            tmp_path,
            "from odoo import models\n\nclass A(models.Model):\n"
            "    _name = 'x.a'\n    _sql_constraints = []\n",
        )
        == []
    )


def test_plain_python_class_is_not_flagged(tmp_path: Path):
    assert (
        _check(
            tmp_path,
            "class Helper:\n    _sql_constraints = [('a', 'unique(b)', 'm')]\n",
        )
        == []
    )


def test_models_constraint_is_not_flagged(tmp_path: Path):
    assert (
        _check(
            tmp_path,
            "from odoo import models\n\nclass A(models.Model):\n"
            "    _name = 'x.a'\n"
            "    _name_uniq = models.Constraint('UNIQUE(name)', 'Must be unique')\n",
        )
        == []
    )


def test_tests_directory_is_skipped(tmp_path: Path):
    path = tmp_path / "mod" / "tests" / "t.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from odoo import models\n\nclass A(models.Model):\n"
        "    _name = 'x.a'\n    _sql_constraints = [('a', 'unique(b)', 'm')]\n"
    )
    assert check_sql_constraints_unsupported(path, "mod", "19.0") == []


def test_rule_only_runs_from_odoo_19():
    meta = next(
        m
        for m, _ in default_registry.get_rules()
        if m.name == "sql-constraints-unsupported"
    )
    assert meta.min_version == "19.0"


def test_migration_scripts_are_skipped(tmp_path: Path):
    path = tmp_path / "mod" / "migrations" / "18.0.1.0" / "pre.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from odoo import models\n\nclass A(models.Model):\n"
        "    _name = 'x.a'\n    _sql_constraints = [('a', 'unique(b)', 'm')]\n"
    )
    assert check_sql_constraints_unsupported(path, "mod", "19.0") == []
