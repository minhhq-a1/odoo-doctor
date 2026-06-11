"""field-no-string-on-required flags required fields lacking an explicit string."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.correctness.field_no_string_on_required import (
    check_field_no_string_on_required,
)


def _module(tmp_path: Path, model_src: str) -> Path:
    mod = tmp_path / "m"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "depends": [], "data": [], "license": "LGPL-3"}'
    )
    (mod / "models" / "m.py").write_text(model_src)
    return tmp_path


def test_required_without_string_is_flagged(tmp_path: Path):
    root = _module(
        tmp_path,
        dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            code = fields.Char(required=True)
        """),
    )
    ctx = build_project_graph([root], odoo_version="17.0").modules["m"]
    diags = check_field_no_string_on_required(ctx)
    assert any(d.rule == "field-no-string-on-required" for d in diags)


def test_required_with_string_is_not_flagged(tmp_path: Path):
    root = _module(
        tmp_path,
        dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            code = fields.Char(string="Code", required=True)
        """),
    )
    ctx = build_project_graph([root], odoo_version="17.0").modules["m"]
    diags = check_field_no_string_on_required(ctx)
    assert not any(d.rule == "field-no-string-on-required" for d in diags)


def test_optional_field_is_not_flagged(tmp_path: Path):
    root = _module(
        tmp_path,
        dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            note = fields.Char()
        """),
    )
    ctx = build_project_graph([root], odoo_version="17.0").modules["m"]
    diags = check_field_no_string_on_required(ctx)
    assert not any(d.rule == "field-no-string-on-required" for d in diags)
