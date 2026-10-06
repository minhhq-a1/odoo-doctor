"""Several classes of one model inside a single module merge into one ModelInfo."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.graph.module_context import _add_model, build_project_graph
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.parsers.python_models import FieldInfo, ModelInfo


def _model(name, inherit, field, file_path, **extra) -> ModelInfo:
    return ModelInfo(
        name=name,
        inherit=inherit,
        fields={field: FieldInfo(name=field, field_type="Char")},
        file_path=file_path,
        line=3,
        **extra,
    )


DEFINITION = {
    "name": "x.model",
    "inherit": [],
    "field": "alpha",
    "file_path": "defs.py",
    "defines": True,
}
EXTENSION = {
    "name": None,
    "inherit": ["x.model"],
    "field": "beta",
    "file_path": "ext.py",
}


@pytest.mark.parametrize("definition_first", [True, False])
def test_the_definition_is_not_lost_when_an_extension_is_parsed_first(definition_first):
    models: dict[str, ModelInfo] = {}
    parsed = [_model(**DEFINITION, is_abstract=True), _model(**EXTENSION)]
    for m in parsed if definition_first else reversed(parsed):
        _add_model(models, m)

    merged = models["x.model"]
    assert merged.name == "x.model"  # still a definition, whatever the order
    assert set(merged.fields) == {"alpha", "beta"}
    assert merged.is_abstract is True
    assert merged.file_path == "defs.py"  # where the model is defined


def test_the_inherit_list_keeps_a_stable_order():
    models: dict[str, ModelInfo] = {}
    _add_model(models, _model("x.model", ["zeta", "alpha"], "a", "defs.py"))
    _add_model(models, _model(None, ["x.model", "alpha", "mid"], "b", "ext.py"))
    assert models["x.model"].inherit == ["zeta", "alpha", "x.model", "mid"]


def _write(tmp_path: Path, files: dict[str, str]) -> Path:
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "17.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("")
    for name, body in files.items():
        (addon / "models" / name).write_text(body)
    return tmp_path


@pytest.mark.parametrize(
    "ext_file, def_file", [("a_ext.py", "z_defs.py"), ("z_ext.py", "a_defs.py")]
)
def test_a_module_that_extends_and_defines_a_model_owns_it(
    tmp_path: Path, ext_file: str, def_file: str
):
    _write(
        tmp_path,
        {
            ext_file: (
                "from odoo import fields, models\n\n"
                "class Ext(models.Model):\n    _inherit = 'x.model'\n\n"
                "    beta = fields.Char()\n"
            ),
            def_file: (
                "from odoo import fields, models\n\n"
                "class Defs(models.Model):\n    _name = 'x.model'\n\n"
                "    alpha = fields.Char()\n"
            ),
        },
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")

    owner = graph.resolver.owner_module_for_model("x.model")
    assert owner.status == ResolveResult.FOUND and owner.source == "mod"
    assert (
        graph.resolver.resolve_field("x.model", "alpha").status == ResolveResult.FOUND
    )
    assert graph.resolver.resolve_field("x.model", "beta").status == ResolveResult.FOUND
