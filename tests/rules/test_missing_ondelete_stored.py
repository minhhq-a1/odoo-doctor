"""`ondelete` configures a foreign-key column: a Many2one that is not stored has none."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete

MODEL = """from odoo import fields, models

class X(models.Model):
    _name = 'x.model'
    _description = 'X'

    plain = fields.Many2one('x.other')
    comp_stored = fields.Many2one('x.other', compute='_c', store=True)
    comp = fields.Many2one('x.other', compute='_c')
    rel = fields.Many2one(related='plain.parent_id')
    rel_stored = fields.Many2one(related='plain.parent_id', store=True)
    explicit = fields.Many2one('x.other', ondelete='cascade')

class Other(models.Model):
    _name = 'x.other'
    _description = 'Other'
"""


def test_only_stored_many2one_fields_need_an_ondelete_policy(tmp_path: Path):
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "17.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("from . import m\n")
    (addon / "models" / "m.py").write_text(MODEL)
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]

    flagged = sorted(d.title.split("'")[1] for d in check_missing_ondelete(ctx))

    assert flagged == ["comp_stored", "plain", "rel_stored"]
