# tests/rules/test_correctness_rules.py
"""Tests for correctness rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.correctness.override_missing_super import (
    check_override_missing_super,
)


def test_override_create_missing_super_catches(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def create(self, vals):
                return {}
    """)
    f = tmp_path / "bad.py"
    f.write_text(code)
    diags = check_override_missing_super(f, "test_mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "override-missing-super"
    assert diags[0].line == 6


def test_override_write_with_super_silent(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def write(self, vals):
                # some custom logic
                return super().write(vals)
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_override_missing_super(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_batch_create_with_super_silent(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def create(self, vals_list):
                return super().create(vals_list)
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_override_missing_super(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_override_read_not_flagged(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def read(self, fields):
                return []
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_override_missing_super(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_non_override_method_silent(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def action_confirm(self):
                self.state = 'confirmed'
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_override_missing_super(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_compute_reads_undeclared_repo_field_catches(tmp_path: Path):
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "1.0", "depends": ["base"]}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            a = fields.Char()
            b = fields.Char()

            @api.depends("a")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.b + rec.a if rec.b else rec.a
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    # The compute reads rec.b (which is 'b') but 'b' is not in depends.
    # 'b' is a known field in the repo.
    assert len(diags) == 1
    assert diags[0].rule == "compute-missing-depends"
    assert diags[0].severity == "warning"
    assert "b" in diags[0].message


def test_compute_declared_field_silent(tmp_path: Path):
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "1.0", "depends": ["base"]}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            a = fields.Char()
            b = fields.Char()

            @api.depends("a", "b")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.b + rec.a if rec.b else rec.a
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    assert len(diags) == 0


def test_compute_dotted_depends_covers_first_segment(tmp_path: Path):
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "1.0", "depends": ["base"]}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            partner_id = fields.Many2one("res.partner")
            b = fields.Char()

            @api.depends("partner_id.name")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.partner_id.name
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    assert len(diags) == 0


def test_compute_undeclared_unknown_field_silent(tmp_path: Path):
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "1.0", "depends": ["base"]}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            a = fields.Char()

            @api.depends("a")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.mystery
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    assert len(diags) == 0


def test_compute_ignores_method_calls(tmp_path: Path):
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )
    from odoo_doctor.graph.module_context import build_project_graph

    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "1.0", "depends": ["base"]}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            a = fields.Char()

            @api.depends("a")
            def _compute_b(self):
                for rec in self:
                    rec.ensure_one()
                    rec.b = rec.a
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    assert len(diags) == 0
