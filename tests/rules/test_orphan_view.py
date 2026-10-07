"""orphan-view flags views that nothing references."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.orphan_view import check_orphan_view


def _manifest(files: list[str]) -> str:
    joined = ", ".join(f'"{f}"' for f in files)
    return '{"name": "M", "depends": [], "data": [' + joined + '], "license": "LGPL-3"}'


def _view(xml_id: str, model: str = "my.model", arch: str = "<form/>", extra="") -> str:
    return f"""  <record id="{xml_id}" model="ir.ui.view">
    <field name="model">{model}</field>{extra}
    <field name="arch" type="xml">{arch}</field>
  </record>
"""


def _scan(tmp_path: Path, xml: str, py: str = ""):
    mod = tmp_path / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "views" / "v.xml").write_text(f"<odoo>\n{xml}</odoo>")
    if py:
        (mod / "models.py").write_text(py)
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    return sorted(d.title for d in check_orphan_view(ctx))


def test_default_view_of_a_model_is_not_flagged(tmp_path: Path):
    """Odoo picks a model's primary view of each type on its own: no reference needed."""
    assert _scan(tmp_path, _view("only_form")) == []


def test_extra_unreferenced_primary_view_is_flagged(tmp_path: Path):
    titles = _scan(tmp_path, _view("default_form") + _view("extra_form"))
    assert titles == ["View 'extra_form' is not referenced"]


def test_lowest_priority_number_is_the_default(tmp_path: Path):
    xml = _view("late_form", extra='\n    <field name="priority">20</field>') + _view(
        "early_form", extra='\n    <field name="priority">5</field>'
    )
    assert _scan(tmp_path, xml) == ["View 'late_form' is not referenced"]


def test_different_types_or_models_do_not_compete(tmp_path: Path):
    xml = (
        _view("a_form")
        + _view("a_list", arch="<list/>")
        + _view("a_tree", arch="<tree/>", model="my.model")
        + _view("b_form", model="other.model")
    )
    # a_list and a_tree are both the list type: the second one is the extra view
    assert _scan(tmp_path, xml) == ["View 'a_tree' is not referenced"]


def test_qweb_view_record_is_never_an_orphan(tmp_path: Path):
    xml = _view("first_form") + _view("tpl", arch="<t t-name='x'/>")
    assert _scan(tmp_path, xml) == []


def test_extra_view_referenced_from_python_is_not_flagged(tmp_path: Path):
    xml = _view("default_form") + _view("extra_form")
    py = "def act(self):\n    return self.env.ref('m.extra_form')\n"
    assert _scan(tmp_path, xml, py) == []


def test_extra_view_referenced_from_a_context_is_not_flagged(tmp_path: Path):
    xml = _view("default_form") + _view("extra_form")
    xml += """  <record id="act" model="ir.actions.act_window">
    <field name="context">{'form_view_ref': 'm.extra_form'}</field>
  </record>
"""
    assert _scan(tmp_path, xml) == []


def test_view_referenced_by_action_is_not_flagged(tmp_path: Path):
    mod = tmp_path / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/v.xml"]))
    (mod / "views" / "v.xml").write_text(
        """<odoo>
  <record id="used_form" model="ir.ui.view">
    <field name="model">my.model</field>
    <field name="arch" type="xml"><form/></field>
  </record>
  <record id="act" model="ir.actions.act_window">
    <field name="view_id" ref="used_form"/>
  </record>
</odoo>"""
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["m"]
    diags = check_orphan_view(ctx)
    assert not any(d.rule == "orphan-view" for d in diags)
