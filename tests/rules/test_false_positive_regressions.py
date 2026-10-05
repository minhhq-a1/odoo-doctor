"""Regression tests for false positives found scanning real OCA/custom addons (0.5.1)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete
from odoo_doctor.rules.manifest.data_order_risk import check_data_order_risk
from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency
from odoo_doctor.rules.performance.create_write_in_loop import (
    check_create_in_loop,
    check_write_in_loop,
)
from odoo_doctor.rules.performance.n_plus_one_read import check_n_plus_one_read
from odoo_doctor.rules.performance.search_in_loop import check_search_in_loop
from odoo_doctor.rules.performance.unbounded_search import check_unbounded_search
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found
from odoo_doctor.rules.xml.missing_xml_ref import check_missing_xml_ref
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model


def _addon(
    root: Path,
    name: str,
    *,
    depends: list[str] | None = None,
    data: list[str] | None = None,
    files: dict[str, str] | None = None,
) -> Path:
    mod = root / name
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        repr(
            {
                "name": name,
                "version": "17.0.1.0.0",
                "depends": ["base"] if depends is None else depends,
                "data": data or [],
                "license": "LGPL-3",
            }
        )
    )
    for rel, content in (files or {}).items():
        target = mod / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content))
    return mod


# --- missing-xml-ref: implicit ir.model xml ids -------------------------------

_MODEL_PY = """\
    from odoo import models, fields

    class MyModel(models.Model):
        _name = "my.model"
        name = fields.Char()
"""


def _rule_xml(ref: str) -> str:
    return f"""\
    <odoo>
      <record id="my_rule" model="ir.rule">
        <field name="name">my rule</field>
        <field name="model_id" ref="{ref}"/>
        <field name="domain_force">[(1, '=', 1)]</field>
      </record>
    </odoo>
    """


def test_implicit_model_xml_id_resolves(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["security/rule.xml"],
        files={
            "models/m.py": _MODEL_PY,
            "security/rule.xml": _rule_xml("model_my_model"),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_missing_xml_ref(ctx) == []


def test_implicit_model_xml_id_qualified_resolves(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["security/rule.xml"],
        files={
            "models/m.py": _MODEL_PY,
            "security/rule.xml": _rule_xml("mod.model_my_model"),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_missing_xml_ref(ctx) == []


def test_implicit_model_xml_id_for_unknown_model_still_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["security/rule.xml"],
        files={
            "models/m.py": _MODEL_PY,
            "security/rule.xml": _rule_xml("model_does_not_exist"),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    diags = check_missing_xml_ref(ctx)
    assert len(diags) == 1
    assert "model_does_not_exist" in diags[0].message


# --- missing-ondelete: required Many2one defaults to restrict -----------------


def _ondelete_diags(tmp_path: Path, field_def: str):
    _addon(
        tmp_path,
        "mod",
        files={
            "models/m.py": f"""\
            from odoo import models, fields

            class MyModel(models.Model):
                _name = "my.model"
                partner_id = {field_def}
            """
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    return check_missing_ondelete(ctx)


def test_required_many2one_is_not_flagged(tmp_path: Path):
    assert (
        _ondelete_diags(tmp_path, 'fields.Many2one("res.partner", required=True)') == []
    )


def test_optional_many2one_is_still_flagged(tmp_path: Path):
    assert len(_ondelete_diags(tmp_path, 'fields.Many2one("res.partner")')) == 1


# --- manifest-missing-dependency: transitive dependencies ---------------------

_SALE_INHERIT_PY = """\
    from odoo import models

    class SaleOrder(models.Model):
        _inherit = "sale.order"
"""


def test_dependency_satisfied_transitively_by_repo_module(tmp_path: Path):
    _addon(tmp_path, "mid", depends=["base", "sale"])
    _addon(
        tmp_path,
        "child",
        depends=["mid"],
        files={"models/s.py": _SALE_INHERIT_PY},
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["child"]
    assert check_missing_dependency(ctx) == []


def test_dependency_unknown_transitive_closure_downgrades_confidence(tmp_path: Path):
    # 'purchase_stock' is a core module we have no manifest for: it may well depend
    # on 'sale', so we cannot assert with HIGH confidence that 'sale' is missing.
    _addon(
        tmp_path,
        "child",
        depends=["purchase_stock"],
        files={"models/s.py": _SALE_INHERIT_PY},
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["child"]
    diags = check_missing_dependency(ctx)
    assert len(diags) == 1
    assert diags[0].confidence == "medium"


def test_dependency_missing_with_fully_known_closure_stays_high(tmp_path: Path):
    _addon(
        tmp_path,
        "child",
        depends=["base"],
        files={"models/s.py": _SALE_INHERIT_PY},
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["child"]
    diags = check_missing_dependency(ctx)
    assert len(diags) == 1
    assert diags[0].confidence == "high"


# --- view-field / button method via prototype inheritance (_inherit + _name) --

_PROTO_PY = """\
    from odoo import models, fields

    class Parent(models.TransientModel):
        _name = "parent.wiz"
        job_ids = fields.Many2many("res.partner")

        def action_parent(self):
            return True

    class Child(models.TransientModel):
        _inherit = "parent.wiz"
        _name = "child.wiz"
"""


def _proto_view_xml(inner: str) -> str:
    return f"""\
    <odoo>
      <record id="view_child" model="ir.ui.view">
        <field name="name">child</field>
        <field name="model">child.wiz</field>
        <field name="arch" type="xml">
          <form>{inner}</form>
        </field>
      </record>
    </odoo>
    """


def test_view_field_from_prototype_parent_is_found(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["views/v.xml"],
        files={
            "models/m.py": _PROTO_PY,
            "views/v.xml": _proto_view_xml('<field name="job_ids"/>'),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_view_field_not_in_model(ctx) == []


def test_view_field_missing_everywhere_still_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["views/v.xml"],
        files={
            "models/m.py": _PROTO_PY,
            "views/v.xml": _proto_view_xml('<field name="nope"/>'),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert len(check_view_field_not_in_model(ctx)) == 1


def test_button_method_from_prototype_parent_is_found(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["views/v.xml"],
        files={
            "models/m.py": _PROTO_PY,
            "views/v.xml": _proto_view_xml(
                '<button name="action_parent" type="object"/>'
            ),
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_button_method_not_found(ctx) == []


# --- search-in-loop: browse() does not query ----------------------------------


def _write(tmp_path: Path, rel: str, code: str) -> Path:
    f = tmp_path / "mod" / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(code))
    return f


def test_browse_in_loop_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        "models/m.py",
        """\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def run(self, ids):
                for i in ids:
                    rec = self.env["res.partner"].browse(i)
        """,
    )
    assert check_search_in_loop(f, "mod", "17.0") == []


def test_search_in_loop_is_still_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        "models/m.py",
        """\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def run(self, ids):
                for i in ids:
                    rec = self.env["res.partner"].search([("id", "=", i)])
        """,
    )
    assert len(check_search_in_loop(f, "mod", "17.0")) == 1


# --- performance rules ignore test code ---------------------------------------

_LOOP_CODE = """\
    from odoo import models

    class X(models.Model):
        _name = "x"

        def run(self, vals):
            for v in vals:
                self.env["res.partner"].search([("id", "=", v)])
                self.env["res.partner"].create({"name": v})
                self.write({"name": v})
            self.env["res.partner"].search([])
            for rec in self:
                rec.partner_id.country_id.state_ids
"""


def _perf_diags(f: Path):
    out = []
    for check in (
        check_search_in_loop,
        check_create_in_loop,
        check_write_in_loop,
        check_n_plus_one_read,
        check_unbounded_search,
    ):
        out += check(f, "mod", "17.0")
    return out


def test_performance_rules_flag_production_code(tmp_path: Path):
    f = _write(tmp_path, "models/m.py", _LOOP_CODE)
    rules = {d.rule for d in _perf_diags(f)}
    assert {"search-in-loop", "create-in-loop", "write-in-loop"} <= rules


def test_performance_rules_skip_tests_directory(tmp_path: Path):
    f = _write(tmp_path, "tests/test_m.py", _LOOP_CODE)
    assert _perf_diags(f) == []


def test_tests_directory_above_addon_does_not_hide_findings(tmp_path: Path):
    # The addon itself lives under a directory called "tests" (like this repo's
    # fixtures); only a tests/ dir *inside* the addon counts as test code.
    f = _write(tmp_path / "tests" / "fixtures", "models/m.py", _LOOP_CODE)
    assert {d.rule for d in _perf_diags(f)} >= {"search-in-loop"}


# --- manifest-data-order-risk: file name beats directory ----------------------


def test_menu_file_in_security_dir_is_not_a_security_file(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["views/v_views.xml", "security/qa_menu.xml"],
        files={
            "views/v_views.xml": "<odoo/>",
            "security/qa_menu.xml": "<odoo/>",
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert check_data_order_risk(ctx) == []


def test_real_security_file_after_views_still_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        data=["views/v_views.xml", "security/ir.model.access.csv"],
        files={
            "views/v_views.xml": "<odoo/>",
            "security/ir.model.access.csv": "id,name\n",
        },
    )
    ctx = build_project_graph([tmp_path], odoo_version="17.0").modules["mod"]
    assert len(check_data_order_risk(ctx)) == 1
