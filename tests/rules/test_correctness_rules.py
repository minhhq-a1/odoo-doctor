# tests/rules/test_correctness_rules.py
"""Tests for correctness rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent, indent

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


def _super_diags(tmp_path: Path, body: str, header: str = "") -> list:
    code = (
        "from odoo import models\n\n"
        "class X(models.Model):\n"
        '    _name = "x"\n' + header + "\n" + indent(dedent(body), "    ")
    )
    f = tmp_path / "m.py"
    f.write_text(code)
    return check_override_missing_super(f, "test_mod", "19.0")


def test_override_that_only_raises_is_not_reported(tmp_path: Path):
    body = """\
        def copy(self, default=None):
            \"\"\"Frozen.\"\"\"
            raise UserError("no")
    """
    assert _super_diags(tmp_path, body) == []


def test_override_with_conditional_raise_still_high(tmp_path: Path):
    body = """\
        def unlink(self):
            if not self:
                raise ValueError("nothing")
            return True
    """
    (diag,) = _super_diags(tmp_path, body)
    assert diag.confidence == "high"


def test_override_that_raises_after_a_return_path_still_high(tmp_path: Path):
    body = """\
        def write(self, vals):
            if vals:
                return True
            raise ValueError("empty")
    """
    (diag,) = _super_diags(tmp_path, body)
    assert diag.confidence == "high"


def test_delegation_to_same_method_of_another_recordset_is_medium(tmp_path: Path):
    body = """\
        def copy(self, default=None):
            return self.mapped("tmpl_id").copy(default=default)
    """
    (diag,) = _super_diags(tmp_path, body)
    assert diag.confidence == "medium"


def test_call_of_same_name_on_self_is_not_a_delegation(tmp_path: Path):
    body = """\
        def create(self, vals):
            return self.create({})
    """
    (diag,) = _super_diags(tmp_path, body)
    assert diag.confidence == "high"


def test_model_without_own_table_is_medium(tmp_path: Path):
    body = """\
        def create(self, vals_list):
            return self
    """
    (diag,) = _super_diags(tmp_path, body, header="    _auto = False\n")
    assert diag.confidence == "medium"


def test_compute_reads_undeclared_repo_field_catches(tmp_path: Path):
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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
            c = fields.Char()

            @api.depends("a")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.a + rec.c if rec.c else rec.a
        """)
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["my_mod"]
    diags = check_compute_missing_depends(ctx)
    # The compute reads rec.c, a known field of the repo that is not in depends.
    assert len(diags) == 1
    assert diags[0].rule == "compute-missing-depends"
    assert diags[0].severity == "warning"
    assert "'c'" in diags[0].message


def test_compute_reading_its_own_output_is_not_a_missing_dependency(tmp_path: Path):
    """What the method assigns is its result, not an input: `team.x = ...; team.x > limit`."""
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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

            total = fields.Integer(compute="_compute_total")
            exceeded = fields.Boolean(compute="_compute_total")
            limit = fields.Integer()
            count = fields.Integer()

            @api.depends("count", "limit")
            def _compute_total(self):
                for rec in self:
                    rec.total = rec.count * 2
                    rec.exceeded = rec.total > rec.limit
                    rec.count += 0
        """)
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["my_mod"]
    # `total` and `exceeded` are assigned here; `count` and `limit` are declared
    assert check_compute_missing_depends(ctx) == []


def test_compute_declared_field_silent(tmp_path: Path):
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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
    from odoo_doctor.graph.module_context import build_project_graph
    from odoo_doctor.rules.correctness.compute_missing_depends import (
        check_compute_missing_depends,
    )

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
