# tests/rules/test_security_csv_ambiguity.py
"""Access-CSV model-name ambiguity (A6): no false positive on real core models with
underscored segments; a genuinely-missing local model still fires."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.unknown_model_in_access_csv import (
    check_unknown_model_in_access_csv,
)

_CSV_HEADER = "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"


def _module(tmp_path: Path, csv_body: str, model_py: str | None = None) -> Path:
    mod = tmp_path / "acl_mod"
    (mod / "security").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "ACL", "depends": [], "data": ["security/ir.model.access.csv"], "license": "LGPL-3"}'
    )
    (mod / "security" / "ir.model.access.csv").write_text(_CSV_HEADER + csv_body)
    if model_py:
        (mod / "models").mkdir()
        (mod / "models" / "m.py").write_text(model_py)
    return tmp_path


def test_act_window_access_row_no_false_positive(tmp_path: Path):
    root = _module(
        tmp_path,
        "access_actwin,access.actwin,model_ir_actions_act_window,,1,0,0,0\n",
    )
    graph = build_project_graph([root], odoo_version="17.0")
    ctx = graph.modules["acl_mod"]
    assert check_unknown_model_in_access_csv(ctx) == []


def test_local_typo_model_still_flagged(tmp_path: Path):
    root = _module(
        tmp_path,
        "access_typo,access.typo,model_my_typo_model,,1,0,0,0\n",
    )
    graph = build_project_graph([root], odoo_version="17.0")
    ctx = graph.modules["acl_mod"]
    diags = check_unknown_model_in_access_csv(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "unknown-model-in-access-csv"
