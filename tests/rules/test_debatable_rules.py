"""Regression tests for the three debatable findings from the 0.5.x real-addon scans."""

from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.data_integrity.data_noupdate_risk import (
    check_data_noupdate_risk,
)
from odoo_doctor.rules.manifest.fixers import fix_missing_required_field
from odoo_doctor.rules.manifest.missing_required_fields import (
    check_missing_required_fields,
)
from odoo_doctor.rules.security.raw_sql_interpolation import (
    check_raw_sql_interpolation,
)


def _addon(root: Path, manifest: dict, files: dict[str, str] | None = None) -> Path:
    mod = root / "mod"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(repr(manifest))
    for rel, content in (files or {}).items():
        target = mod / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content))
    return mod


_FULL = {
    "name": "mod",
    "version": "17.0.1.0.0",
    "depends": ["base"],
    "license": "LGPL-3",
}


# --- data-noupdate-risk: ir.rule is a convention, not a defect ----------------


def _noupdate_diags(tmp_path: Path, model: str):
    _addon(
        tmp_path,
        {**_FULL, "data": ["data/d.xml"]},
        {
            "data/d.xml": f"""\
            <odoo>
              <record id="rec" model="{model}">
                <field name="name">x</field>
              </record>
            </odoo>
            """
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    return check_data_noupdate_risk(ctx)


def test_ir_rule_without_noupdate_is_medium_confidence(tmp_path: Path):
    diags = _noupdate_diags(tmp_path, "ir.rule")
    assert [d.confidence for d in diags] == ["medium"]


def test_ir_config_parameter_without_noupdate_stays_high(tmp_path: Path):
    diags = _noupdate_diags(tmp_path, "ir.config_parameter")
    assert [d.confidence for d in diags] == ["high"]


# --- raw-sql-string-interpolation: honour `# pylint: disable=sql-injection` ----


def _sql_diags(tmp_path: Path, code: str):
    f = tmp_path / "m.py"
    f.write_text(dedent(code))
    return check_raw_sql_interpolation(f, "mod", "17.0")


def test_unmarked_dynamic_sql_is_still_flagged(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            query = f"SELECT 1 FROM t WHERE {where}"
            self.env.cr.execute(query, args)
        """,
    )
    assert len(diags) == 1


def test_pylint_disable_comment_in_function_suppresses(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            # pylint: disable=sql-injection
            # values are bound through args below
            query = f"SELECT 1 FROM t WHERE {where}"
            self.env.cr.execute(query, args)
        """,
    )
    assert diags == []


def test_pylint_disable_trailing_comment_suppresses_that_line(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            query = f"SELECT 1 FROM t WHERE {where}"
            self.env.cr.execute(query, args)  # pylint: disable=sql-injection
        """,
    )
    assert diags == []


def test_pylint_disable_with_several_checks_suppresses(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            # pylint: disable=line-too-long,sql-injection
            self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)
        """,
    )
    assert diags == []


def test_pylint_disable_does_not_leak_into_other_functions(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def safe(self, where, args):
            # pylint: disable=sql-injection
            self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)

        def unsafe(self, where, args):
            self.env.cr.execute(f"SELECT 2 FROM t WHERE {where}", args)
        """,
    )
    assert [d.line for d in diags] == [6]


def test_pylint_disable_does_not_cover_code_before_the_comment(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)
            # pylint: disable=sql-injection
            self.env.cr.execute(f"SELECT 2 FROM t WHERE {where}", args)
        """,
    )
    assert [d.line for d in diags] == [2]


def test_unrelated_pylint_disable_does_not_suppress(tmp_path: Path):
    diags = _sql_diags(
        tmp_path,
        """\
        def run(self, where, args):
            # pylint: disable=line-too-long
            self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)
        """,
    )
    assert len(diags) == 1


# --- manifest-missing-required-fields: defaults are not "missing" -------------


def _required_titles(tmp_path: Path, manifest: dict) -> set[str]:
    _addon(tmp_path, manifest)
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    return {
        d.title.rsplit(": ", 1)[-1].strip("'")
        for d in check_missing_required_fields(ctx)
    }


def test_installable_is_not_required(tmp_path: Path):
    assert _required_titles(tmp_path, {**_FULL, "data": []}) == set()


def test_data_not_required_when_manifest_declares_assets(tmp_path: Path):
    manifest = {**_FULL, "assets": {"web.assets_backend": ["mod/static/a.js"]}}
    assert _required_titles(tmp_path, manifest) == set()


def test_data_still_required_without_assets_or_demo(tmp_path: Path):
    assert _required_titles(tmp_path, dict(_FULL)) == {"data"}


def test_minimal_manifest_reports_core_fields_only(tmp_path: Path):
    assert _required_titles(tmp_path, {"name": "mod"}) == {
        "version",
        "depends",
        "data",
        "license",
    }


def _fixer_diag():
    from odoo_doctor.core.diagnostics import Diagnostic

    return Diagnostic(
        module="m",
        file_path="m/__manifest__.py",
        line=1,
        column=0,
        rule="manifest-missing-required-fields",
        category="Module Hygiene",
        severity="warning",
        tier="P2",
        source="native",
        confidence="high",
        title="t",
        message="m",
        help="h",
        odoo_version="17.0",
    )


def test_fixer_does_not_add_installable(tmp_path: Path):
    out = fix_missing_required_field(_fixer_diag(), "{'name': 'M'}")
    assert "installable" not in ast.literal_eval(out)


def test_fixer_does_not_add_data_to_asset_only_manifest(tmp_path: Path):
    src = "{'name': 'M', 'version': '1', 'depends': ['web'], 'license': 'LGPL-3', 'assets': {'a': []}}"
    assert fix_missing_required_field(_fixer_diag(), src) == src
