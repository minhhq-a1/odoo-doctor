"""A model a module only extends does not need an access rule in that module's CSV."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.missing_access_csv import check_missing_access_csv

HEADER = (
    "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
)

MODELS = """from odoo import fields, models

class Own(models.Model):
    _name = 'x.own'
    _description = 'Own'

class Core(models.Model):
    _name = 'res.core'
    _inherit = ['res.core', 'mail.thread']

class Plain(models.Model):
    _inherit = 'res.other'

    note = fields.Char()
"""


def _module(tmp_path: Path, csv_rows: str | None):
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "17.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("from . import m\n")
    (addon / "models" / "m.py").write_text(MODELS)
    if csv_rows is not None:
        (addon / "security").mkdir()
        (addon / "security" / "ir.model.access.csv").write_text(HEADER + csv_rows)
    return build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]


@pytest.mark.parametrize(
    "csv_rows",
    [
        None,  # no CSV at all
        "a_other,a,model_res_other,base.group_user,1,0,0,0\n",  # a CSV that lacks x.own
    ],
    ids=["no-csv", "csv-without-the-model"],
)
def test_only_a_model_the_module_defines_needs_an_access_rule(tmp_path: Path, csv_rows):
    diags = check_missing_access_csv(_module(tmp_path, csv_rows))
    # x.own is defined here; res.core (a self-extension) and res.other are only extended
    assert len(diags) == 1
    assert "'x.own'" in diags[0].message
