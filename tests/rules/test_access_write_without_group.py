"""access-write-without-group: an ACL row with no group applies to every user, portal and public too."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.access_write_without_group import (
    check_access_write_without_group,
)

HEADER = (
    "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
)

MODELS = """from odoo import models

class Own(models.Model):
    _name = 'x.own'
    _description = 'Own'

class Wiz(models.TransientModel):
    _name = 'x.wiz'
    _description = 'Wizard'
"""


def _diags(tmp_path: Path, rows: str):
    addon = tmp_path / "mod"
    (addon / "models").mkdir(parents=True)
    (addon / "security").mkdir()
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "17.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "__init__.py").write_text("from . import models\n")
    (addon / "models" / "__init__.py").write_text("from . import m\n")
    (addon / "models" / "m.py").write_text(MODELS)
    (addon / "security" / "ir.model.access.csv").write_text(HEADER + rows)
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    return check_access_write_without_group(ctx)


@pytest.mark.parametrize(
    "perms", ["1,1,0,0", "1,0,0,1", "1,1,1,1", "0,1,0,0"], ids=lambda p: p
)
def test_write_or_unlink_without_a_group_is_high_confidence(tmp_path: Path, perms):
    diags = _diags(tmp_path, f"a_own,a,model_x_own,,{perms}\n")
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "access-write-without-group",
        "P1",
        "Security",
        "high",
    )
    assert d.line == 2  # the CSV row, header is line 1
    assert d.file_path.endswith("ir.model.access.csv")
    assert "x_own" in d.message or "x.own" in d.message


def test_create_alone_is_medium_confidence(tmp_path: Path):
    # public forms create records anonymously on purpose, so this is a review item
    diags = _diags(tmp_path, "a_own,a,model_x_own,,1,0,1,0\n")
    assert [d.confidence for d in diags] == ["medium"]


@pytest.mark.parametrize("perms", ["1,0,0,0", "0,0,0,0"], ids=lambda p: p)
def test_read_only_or_empty_rows_are_fine(tmp_path: Path, perms):
    assert _diags(tmp_path, f"a_own,a,model_x_own,,{perms}\n") == []


@pytest.mark.parametrize("group", ["base.group_user", "mod.group_x"])
def test_a_row_with_a_group_is_fine(tmp_path: Path, group):
    assert _diags(tmp_path, f"a_own,a,model_x_own,{group},1,1,1,1\n") == []


def test_a_transient_model_is_skipped(tmp_path: Path):
    # wizards are routinely opened by anyone and hold throw-away rows
    assert _diags(tmp_path, "a_wiz,a,model_x_wiz,,1,1,1,1\n") == []


def test_one_finding_per_row_and_other_rows_do_not_hide_it(tmp_path: Path):
    rows = (
        "a_1,a,model_x_own,base.group_user,1,1,1,1\n"
        "a_2,b,model_x_own,,1,1,1,1\n"
        "a_3,c,model_x_wiz,,1,1,1,1\n"
        "a_4,d,model_base_res_partner,,1,1,0,0\n"
    )
    diags = _diags(tmp_path, rows)
    assert sorted(d.line for d in diags) == [3, 5]


def test_no_csv_means_no_findings(tmp_path: Path):
    addon = tmp_path / "mod"
    addon.mkdir()
    (addon / "__manifest__.py").write_text(
        repr(
            {"name": "mod", "version": "17.0.1.0.0", "depends": [], "license": "LGPL-3"}
        )
    )
    (addon / "__init__.py").write_text("")
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_access_write_without_group(ctx) == []
