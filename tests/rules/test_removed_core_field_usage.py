"""removed-core-field-usage: fields core models lost in Odoo 18 / 19."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.removed_core_field_usage import (
    check_removed_core_field_usage,
)

from ._module import module_ctx, view


def _diags(tmp_path: Path, files: dict[str, str], version="19.0"):
    return check_removed_core_field_usage(module_ctx(tmp_path, files, version))


def record(model: str, field: str, body: str = "X") -> str:
    return (
        f'<odoo><record id="r" model="{model}">\n'
        f'<field name="name">n</field>\n<field name="{field}">{body}</field>\n'
        "</record></odoo>"
    )


@pytest.mark.parametrize(
    "model,field",
    [
        ("res.users", "groups_id"),
        ("ir.ui.menu", "groups_id"),
        ("ir.actions.server", "groups_id"),
        ("res.groups", "category_id"),
        ("res.groups", "users"),
        ("res.partner", "mobile"),
        ("account.account", "deprecated"),
        ("ir.filters", "user_id"),
    ],
)
def test_removed_fields_in_data_records_are_flagged(
    tmp_path: Path, model: str, field: str
):
    diags = _diags(tmp_path, {"d.xml": record(model, field)})
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "removed-core-field-usage",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert field in d.title and model in d.title
    assert d.line == 3


def test_detailed_type_is_gone_from_odoo_18(tmp_path: Path):
    xml = record("product.template", "detailed_type", "service")
    assert len(_diags(tmp_path, {"d.xml": xml}, "18.0")) == 1
    assert _diags(tmp_path, {"d.xml": xml}, "17.0") == []


def test_groups_id_is_still_valid_in_odoo_18(tmp_path: Path):
    assert _diags(tmp_path, {"d.xml": record("res.users", "groups_id")}, "18.0") == []


@pytest.mark.parametrize(
    "model,field",
    [
        ("res.groups", "implied_ids"),
        ("res.groups", "name"),
        ("res.partner", "phone"),
        ("some.model", "groups_id"),
        ("res.users", "group_ids"),
    ],
)
def test_other_fields_and_models_are_not_flagged(tmp_path: Path, model, field):
    assert _diags(tmp_path, {"d.xml": record(model, field)}) == []


def test_view_of_a_model_with_a_removed_field(tmp_path: Path):
    xml = view(
        '<form><field name="groups_id"/><field name="line_ids">'
        '<list><field name="groups_id"/></list></field></form>',
        model="res.users",
    )
    diags = _diags(tmp_path, {"v.xml": xml})
    assert len(diags) == 1  # the nested one belongs to the sub-model


def test_xpath_on_a_removed_field(tmp_path: Path):
    xml = view(
        "<xpath expr=\"//field[@name='groups_id']\" position='after'/>",
        model="res.users",
    )
    assert len(_diags(tmp_path, {"v.xml": xml})) == 1


def test_view_of_an_unrelated_model_is_ignored(tmp_path: Path):
    xml = view('<form><field name="groups_id"/></form>', model="x.model")
    assert _diags(tmp_path, {"v.xml": xml}) == []


PY = (
    "from odoo import fields, models\n\n"
    "class P(models.Model):\n"
    "    _inherit = 'product.template'\n"
    "    detailed_type = fields.Selection(selection_add=[('app', 'App')])\n\n"
    "    def f(self, user):\n"
    "        ids = user.groups_id.ids\n"
    "        vals = {'groups_id': [(4, 1)], 'x': 1}\n"
    "        return self.search([('detailed_type', '=', 'app')]), ids, vals\n"
)


def test_python_references_are_medium_confidence(tmp_path: Path):
    diags = _diags(tmp_path, {"models/m.py": PY})
    assert [(d.line, d.confidence) for d in diags] == [
        (8, "medium"),
        (9, "medium"),
        (10, "medium"),
    ]


def test_compat_probes_and_docstrings_are_skipped(tmp_path: Path):
    py = (
        "def f(user):\n"
        '    """The groups_id field."""\n'
        "    if 'groups_id' in user._fields:\n"
        "        return 1\n"
        "    return hasattr(user, 'groups_id')\n"
    )
    assert _diags(tmp_path, {"models/m.py": py}) == []


def test_branch_guarded_by_a_probe_is_skipped(tmp_path: Path):
    py = (
        "def ids(user):\n"
        "    if 'groups_id' in user._fields:\n"
        "        return user.groups_id.ids\n"
        "    return user.group_ids.ids\n"
        "def other(user):\n"
        "    return user.groups_id\n"
    )
    assert [d.line for d in _diags(tmp_path, {"models/m.py": py})] == [6]


def test_a_model_that_defines_its_own_field_is_left_alone(tmp_path: Path):
    py = (
        "from odoo import fields, models\n\n"
        "class Rule(models.Model):\n"
        "    _name = 'my.rule'\n"
        "    groups_id = fields.Many2many('res.groups')\n\n"
        "    def f(self):\n"
        "        return self.groups_id\n"
    )
    assert _diags(tmp_path, {"models/m.py": py}) == []


def test_python_names_follow_the_version_gate(tmp_path: Path):
    py = "def f(user):\n    return user.groups_id\n"
    assert _diags(tmp_path, {"models/m.py": py}, "18.0") == []
    assert len(_diags(tmp_path, {"models/m.py": py}, "19.0")) == 1
