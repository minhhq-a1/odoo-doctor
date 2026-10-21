"""``_inherit`` / ``_inherits`` written as a tuple or a name: parser and field resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

import odoo_doctor.cli.app  # noqa: F401  (registers the rules)
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.parsers.python_models import parse_models
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model
from tests.rules._module import module_ctx, view

MIXINS = '("mail.thread", "mail.activity.mixin")'


def _parse(tmp_path: Path, body: str):
    f = tmp_path / "m.py"
    f.write_text("from odoo import fields, models\n\n\n" + body)
    return parse_models(f)


def test_tuple_and_list_inherit_give_the_same_parents(tmp_path: Path):
    tup, lst = _parse(
        tmp_path,
        "class A(models.Model):\n    _name = 'a'\n    _inherit = ('x', 'y')\n\n\n"
        "class B(models.Model):\n    _name = 'b'\n    _inherit = ['x', 'y']\n",
    )
    assert tup.inherit == lst.inherit == ["x", "y"]
    assert not tup.inherit_unresolved and not lst.inherit_unresolved
    assert tup.defines


@pytest.mark.parametrize(
    "inherit",
    ["MIXINS", "['a'] + EXTRA", "('a', *EXTRA)", "('a', EXTRA)"],
)
def test_inherit_that_is_not_a_literal_is_unresolved(tmp_path: Path, inherit: str):
    (model,) = _parse(
        tmp_path,
        f"class A(models.Model):\n    _name = 'a'\n    _inherit = {inherit}\n",
    )
    assert model.inherit_unresolved


def test_inherits_with_a_computed_entry_is_unresolved(tmp_path: Path):
    ok, bad = _parse(
        tmp_path,
        "class A(models.Model):\n    _name = 'a'\n    _inherits = {'p': 'p_id'}\n\n\n"
        "class B(models.Model):\n    _name = 'b'\n    _inherits = {PARENT: 'p_id'}\n",
    )
    assert ok.inherits == {"p": "p_id"} and not ok.inherit_unresolved
    assert bad.inherit_unresolved


def _unknown_fields(tmp_path: Path, models_py: str, fields: list[str], model: str):
    arch = "<form>" + "".join(f'<field name="{f}"/>\n' for f in fields) + "</form>"
    ctx = module_ctx(
        tmp_path,
        {"models/m.py": models_py, "views/v.xml": view(arch, model=model)},
        version="17.0",
    )
    return [
        d.title.split("'")[1]
        for d in check_view_field_not_in_model(ctx)
        if d.rule == "view-field-not-in-model"
    ]


HEAD = "from odoo import fields, models\n\n\n"


def test_mail_mixins_given_as_a_tuple_resolve(tmp_path: Path):
    code = (
        HEAD
        + f"class T(models.Model):\n    _name = 'x.t'\n    _inherit = {MIXINS}\n"
        + "    name = fields.Char()\n"
    )
    assert (
        _unknown_fields(tmp_path, code, ["name", "message_ids", "activity_ids"], "x.t")
        == []
    )


def test_parent_given_as_a_tuple_is_searched_for_the_field(tmp_path: Path):
    code = (
        HEAD
        + "class P(models.Model):\n    _name = 'x.p'\n    code = fields.Char()\n\n\n"
        + "class C(models.Model):\n    _name = 'x.c'\n    _inherit = ('x.p',)\n"
        + "    own = fields.Char()\n"
    )
    assert _unknown_fields(tmp_path, code, ["code", "own", "ghost"], "x.c") == ["ghost"]


def test_extension_written_as_a_tuple_adds_its_fields(tmp_path: Path):
    code = (
        HEAD
        + "class P(models.Model):\n    _name = 'x.p'\n\n\n"
        + "class E(models.Model):\n    _inherit = ('x.p',)\n    added = fields.Char()\n"
    )
    assert _unknown_fields(tmp_path, code, ["added", "ghost"], "x.p") == ["ghost"]


@pytest.mark.parametrize("inherit", ["('not.a.known.mixin',)", "MIXINS"])
def test_parents_that_cannot_be_resolved_never_report_a_field_missing(
    tmp_path: Path, inherit: str
):
    code = (
        HEAD
        + "MIXINS = ['a.b']\n\n\n"
        + f"class C(models.Model):\n    _name = 'x.c'\n    _inherit = {inherit}\n"
    )
    assert _unknown_fields(tmp_path, code, ["ghost"], "x.c") == []


BASE_MODEL = (
    HEAD + "class B(models.Model):\n    _name = 'x.base'\n    name = fields.Char()\n"
)


def _project(tmp_path: Path, ext_model: str, fields: list[str]):
    """Addon ``a`` defines x.base; addon ``b`` extends it from another module and
    declares a view on x.base that uses ``fields``. Returns the unknown field names."""
    arch = "<form>" + "".join(f'<field name="{f}"/>\n' for f in fields) + "</form>"
    for name, depends, files in (
        ("a", [], {"models/m.py": BASE_MODEL}),
        (
            "b",
            ["a"],
            {
                "models/m.py": HEAD + ext_model,
                "views/v.xml": view(arch, model="x.base"),
            },
        ),
    ):
        addon = tmp_path / name
        for rel, text in files.items():
            (addon / rel).parent.mkdir(parents=True, exist_ok=True)
            (addon / rel).write_text(text)
        (addon / "__manifest__.py").write_text(
            repr(
                {
                    "name": name,
                    "version": "17.0.1.0.0",
                    "depends": depends,
                    "data": ["views/v.xml"] if name == "b" else [],
                }
            )
        )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["b"]
    return [d.title.split("'")[1] for d in check_view_field_not_in_model(ctx)]


@pytest.mark.parametrize(
    "inherit", ["['x.base', 'mail.thread']", "('x.base', 'mail.thread')"]
)
def test_a_mixin_added_by_an_extension_in_another_module_resolves(
    tmp_path: Path, inherit: str
):
    ext = (
        f"class E(models.Model):\n    _inherit = {inherit}\n    added = fields.Char()\n"
    )
    assert _project(tmp_path, ext, ["name", "added", "message_ids"]) == []


def test_an_extension_with_a_computed_parent_list_leaves_the_model_unresolved(
    tmp_path: Path,
):
    ext = (
        "MIX = ['mail.thread']\n\n\n"
        "class E(models.Model):\n    _inherit = ['x.base'] + MIX\n"
        "    added = fields.Char()\n"
    )
    assert _project(tmp_path, ext, ["name", "added", "ghost"]) == []


def test_an_extension_that_names_no_model_does_not_lose_its_fields(tmp_path: Path):
    ext = (
        "MIX = ['x.base']\n\n\n"
        "class E(models.Model):\n    _inherit = MIX\n    added = fields.Char()\n"
    )
    assert _project(tmp_path, ext, ["name", "added"]) == []


def test_a_field_that_nothing_declares_is_still_reported(tmp_path: Path):
    ext = (
        "class E(models.Model):\n    _inherit = ['x.base']\n    added = fields.Char()\n"
    )
    assert _project(tmp_path, ext, ["name", "added", "ghost"]) == ["ghost"]
