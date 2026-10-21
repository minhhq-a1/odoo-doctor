"""fix_view_tree_removed on Python action dicts: only the literals change."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.upgrade_safety.fixers import fix_view_tree_removed
from odoo_doctor.rules.upgrade_safety.view_tree_removed import check_view_tree_removed

from ._fix import fix_files


def _fix(tmp_path: Path, source: str):
    return fix_files(
        tmp_path, {"m.py": source}, check_view_tree_removed, fix_view_tree_removed
    )


def test_view_mode_literal_replaced_keeping_quotes(tmp_path: Path):
    src = (
        "def a(self):\n"
        "    return {'type': 'ir.actions.act_window', 'res_model': 'x',\n"
        "            'view_mode': 'tree,form'}\n"
        "def b(self):\n"
        '    return {"res_model": "x", "view_mode": "form, tree"}\n'
    )
    diags, texts, result = _fix(tmp_path, src)
    assert len(diags) == 2 and result.skipped_count == 0
    assert texts["m.py"] == src.replace("tree,form", "list,form").replace(
        "form, tree", "form, list"
    )


def test_views_pair_and_view_mode_in_one_dict(tmp_path: Path):
    src = (
        "def a(self):\n"
        "    return {\n"
        "        'res_model': 'x',\n"
        "        'view_mode': 'tree',\n"
        "        'views': [(False, 'tree'), (False, 'form')],\n"
        "        'name': 'tree',\n"
        "    }\n"
    )
    diags, texts, result = _fix(tmp_path, src)
    assert len(diags) == 2 and result.skipped_count == 0
    assert texts["m.py"] == src.replace(
        "'view_mode': 'tree'", "'view_mode': 'list'"
    ).replace("(False, 'tree')", "(False, 'list')")


def test_dict_that_does_not_look_like_an_action_is_not_touched(tmp_path: Path):
    src = "DATA = {'view_mode': 'tree,form'}\n"
    diags, texts, result = _fix(tmp_path, src)
    assert [d.confidence for d in diags] == ["medium"]
    assert texts["m.py"] == src and result.changed_files == {}


def test_crlf_python_is_kept(tmp_path: Path):
    src = "def a(self):\r\n    return {'res_model': 'x', 'view_mode': 'tree'}\r\n"
    _, texts, _ = _fix(tmp_path, src)
    assert texts["m.py"] == src.replace("'tree'", "'list'")


def test_non_ascii_before_the_literal(tmp_path: Path):
    src = "def a(self):\n    return {'name': 'Tableau é', 'res_model': 'x', 'view_mode': 'tree'}\n"
    _, texts, _ = _fix(tmp_path, src)
    assert texts["m.py"] == src.replace("'tree'", "'list'")
