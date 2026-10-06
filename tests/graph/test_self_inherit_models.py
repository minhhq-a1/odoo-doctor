"""`_name = 'x'` together with `_inherit = ['x', mixin]` extends x, it does not redefine it.

Odoo core uses this idiom to add a mixin to an existing model (`pos_hr` does it for
`hr.employee`, `sale` for `account.move`). The resolver must keep the fields and the owner
of the original definition whichever module is discovered last.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.xml.view_field_not_in_model import (
    check_view_field_not_in_model,
)

VIEW = """<odoo>
  <record id="view_x_form" model="ir.ui.view">
    <field name="name">x.form</field>
    <field name="model">x.model</field>
    <field name="arch" type="xml">
      <form>{fields}</form>
    </field>
  </record>
</odoo>
"""


def _addon(root: Path, name: str, depends: list[str], model_py: str, view="") -> None:
    addon = root / name
    (addon / "models").mkdir(parents=True)
    data = []
    if view:
        (addon / "views").mkdir()
        (addon / "views" / "v.xml").write_text(view)
        data = ["views/v.xml"]
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": name,
                "version": "17.0.1.0.0",
                "depends": depends,
                "data": data,
                "license": "LGPL-3",
            }
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("from . import m\n")
    (addon / "models" / "m.py").write_text(model_py)


DEFINER = """from odoo import fields, models

class X(models.Model):
    _name = 'x.model'
    _description = 'X'

    alpha = fields.Char()

    def action_alpha(self):
        return True

class Other(models.Model):
    _name = 'x.other'
    _description = 'Other'
"""

EXTENSION = """from odoo import fields, models

class X(models.Model):
    _name = 'x.model'
    _inherit = ['x.model', 'x.other']

    beta = fields.Char()
"""


# The modules are discovered alphabetically, so these two names cover both the case where
# the extension is parsed after the definition and the case where it is parsed before.
@pytest.fixture(params=[("aaa_defs", "zzz_ext"), ("zzz_defs", "aaa_ext")])
def project(request, tmp_path: Path):
    defs, ext = request.param
    view = VIEW.format(fields='<field name="alpha"/><field name="beta"/>')
    _addon(tmp_path, defs, ["base"], DEFINER, view=view)
    _addon(tmp_path, ext, [defs], EXTENSION)
    return build_project_graph([tmp_path], odoo_version="17.0"), defs, ext


def test_fields_of_the_original_definition_survive_the_extension(project):
    graph, _defs, _ext = project
    resolver = graph.resolver
    assert resolver.resolve_field("x.model", "alpha").status == ResolveResult.FOUND
    assert resolver.resolve_field("x.model", "beta").status == ResolveResult.FOUND


def test_methods_of_the_original_definition_survive_the_extension(project):
    graph, _defs, _ext = project
    found = graph.resolver.resolve_method("x.model", "action_alpha")
    assert found.status == ResolveResult.FOUND


def test_the_owner_is_the_module_that_defines_the_model(project):
    graph, defs, _ext = project
    owner = graph.resolver.owner_module_for_model("x.model")
    assert owner.status == ResolveResult.FOUND and owner.source == defs


def test_a_field_that_exists_nowhere_is_still_reported(project):
    graph, _defs, _ext = project
    # x.model and every ancestor (x.other) are defined in the project: absence is provable
    assert (
        graph.resolver.resolve_field("x.model", "gamma").status
        == ResolveResult.NOT_FOUND
    )


def test_the_modules_own_model_views_are_not_mutated(project):
    graph, defs, ext = project
    assert set(graph.modules[defs].models["x.model"].fields) == {"alpha"}
    assert set(graph.modules[ext].models["x.model"].fields) == {"beta"}


def test_view_field_rule_accepts_fields_of_both_declarations(project):
    graph, defs, _ext = project
    assert check_view_field_not_in_model(graph.modules[defs]) == []


def test_view_field_rule_still_flags_a_missing_field(tmp_path: Path):
    view = VIEW.format(fields='<field name="alpha"/><field name="gamma"/>')
    _addon(tmp_path, "aaa_defs", ["base"], DEFINER, view=view)
    _addon(tmp_path, "zzz_ext", ["aaa_defs"], EXTENSION)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    diags = check_view_field_not_in_model(graph.modules["aaa_defs"])
    assert [d.title for d in diags] == ["View references unknown field 'gamma'"]
