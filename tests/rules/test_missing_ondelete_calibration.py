"""missing-ondelete is advisory: Odoo's default for an optional Many2one is deliberate."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete
from odoo_doctor.rules.registry import default_registry


def _ctx(tmp_path: Path):
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "19.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "models" / "m.py").write_text(
        "from odoo import fields, models\n\n"
        "class X(models.Model):\n"
        "    _name = 'x.model'\n"
        "    _description = 'X'\n\n"
        "    company_id = fields.Many2one('res.company')\n"
    )
    return build_project_graph([tmp_path], odoo_version="19.0").modules["mod"]


def test_finding_is_low_confidence_so_it_never_scores(tmp_path: Path):
    """Odoo 19 community itself leaves about 83% of its optional stored Many2one without
    an ondelete (``company_id``, ``user_id``, ``partner_id``...): the default 'set null'
    is the accepted choice, so flagging it must not cost score."""
    (diag,) = check_missing_ondelete(_ctx(tmp_path))
    assert diag.confidence == "low"
    meta, _ = default_registry.get("missing-ondelete")
    assert meta.default_confidence == "low"


def test_message_states_the_default_instead_of_predicting_integrity_problems(
    tmp_path: Path,
):
    (diag,) = check_missing_ondelete(_ctx(tmp_path))
    assert "set null" in diag.message
    assert "may cause data integrity issues" not in diag.message
