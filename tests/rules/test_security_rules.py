# tests/rules/test_security_rules.py
"""Tests for security rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.raw_sql_interpolation import check_raw_sql_interpolation


def test_raw_sql_fstring(bad_addon: Path):
    """bad_addon uses f-string in SQL."""
    py_file = bad_addon / "models" / "bad_model.py"
    diags = check_raw_sql_interpolation(py_file, "bad_addon", "17.0")
    assert len(diags) >= 1
    assert all(d.rule == "raw-sql-string-interpolation" for d in diags)


def test_raw_sql_percent_format(tmp_path: Path):
    code = dedent("""\
        class M:
            def m(self):
                name = "x"
                self.env.cr.execute("SELECT * FROM res_partner WHERE name = '%s'" % name)
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    diags = check_raw_sql_interpolation(f, "m", "17.0")
    assert len(diags) >= 1


def test_raw_sql_safe_parameterized(tmp_path: Path):
    code = dedent("""\
        class M:
            def m(self):
                self.env.cr.execute("SELECT * FROM res_partner WHERE name = %s", (name,))
    """)
    f = tmp_path / "m.py"
    f.write_text(code)
    diags = check_raw_sql_interpolation(f, "m", "17.0")
    assert diags == []


def test_missing_access_csv_catches_bad_addon(bad_addon: Path):
    from odoo_doctor.rules.security.missing_access_csv import check_missing_access_csv
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_missing_access_csv(ctx)
    assert len(diags) >= 1
    assert all(d.rule == "missing-access-csv" for d in diags)


def test_missing_access_csv_clean(sample_addon: Path):
    from odoo_doctor.rules.security.missing_access_csv import check_missing_access_csv
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_missing_access_csv(ctx)
    # sample_addon has security CSV and its wizard model is transient — no error
    assert diags == []


def test_unknown_model_in_access_csv_flags_current_module_missing_model(tmp_path: Path):
    """Current-module model external IDs are high confidence when absent."""
    from odoo_doctor.rules.security.unknown_model_in_access_csv import (
        check_unknown_model_in_access_csv,
    )

    addon = tmp_path / "x_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "security").mkdir()
    (addon / "__manifest__.py").write_text(
        "{'name': 'X Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': ['security/ir.model.access.csv']}\n"
    )
    (addon / "models" / "m.py").write_text(
        "from odoo import models\n"
        "class XKnown(models.Model):\n"
        "    _name = 'x.known'\n"
    )
    (addon / "security" / "ir.model.access.csv").write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        "access_x_missing,x missing,model_x_missing,,1,0,0,0\n"
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["x_addon"]
    diags = check_unknown_model_in_access_csv(ctx)

    assert len(diags) == 1
    assert diags[0].rule == "unknown-model-in-access-csv"
    assert diags[0].confidence == "high"
    assert "x.missing" in diags[0].message


def test_unknown_model_in_access_csv_does_not_flag_external_unknown_module(tmp_path: Path):
    """External module IDs remain UNKNOWN unless the resolver can prove absence."""
    from odoo_doctor.rules.security.unknown_model_in_access_csv import (
        check_unknown_model_in_access_csv,
    )

    addon = tmp_path / "x_addon"
    (addon / "security").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'X Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': ['security/ir.model.access.csv']}\n"
    )
    (addon / "security" / "ir.model.access.csv").write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        "access_external_missing,external missing,external_module.model_x_missing,,1,0,0,0\n"
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["x_addon"]
    diags = check_unknown_model_in_access_csv(ctx)

    assert diags == []
