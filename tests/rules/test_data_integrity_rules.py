"""Tests for Data Integrity rules."""

from __future__ import annotations

from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph


def _make_addon(
    tmp_path,
    name,
    manifest_extra="",
    models_code="",
    xml_data="",
    xml_filename="data.xml",
):
    mod = tmp_path / name
    mod.mkdir()
    data_list = f'"{xml_filename}"' if xml_data else ""
    (mod / "__manifest__.py").write_text(
        f'{{"name": "{name}", "version": "17.0.1.0.0", "depends": ["base"], '
        f'"data": [{data_list}], "license": "LGPL-3"{manifest_extra}}}'
    )
    if models_code:
        models_dir = mod / "models"
        models_dir.mkdir()
        (models_dir / "models.py").write_text(models_code)
    if xml_data:
        (mod / xml_filename).write_text(xml_data)
    return mod


# --- missing-ondelete tests ---


def test_missing_ondelete_flags_m2o_without_ondelete(tmp_path):
    from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete

    code = dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            partner_id = fields.Many2one("res.partner")
    """)
    _make_addon(tmp_path, "test_mod", models_code=code)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_missing_ondelete(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "missing-ondelete"
    assert "partner_id" in diags[0].title


def test_missing_ondelete_clean_with_explicit_ondelete(tmp_path):
    from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete

    code = dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            partner_id = fields.Many2one("res.partner", ondelete="cascade")
    """)
    _make_addon(tmp_path, "test_mod", models_code=code)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_missing_ondelete(ctx)
    assert diags == []


def test_missing_ondelete_skips_transient(tmp_path):
    from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete

    code = dedent("""\
        from odoo import models, fields

        class MyWizard(models.TransientModel):
            _name = "my.wizard"
            partner_id = fields.Many2one("res.partner")
    """)
    _make_addon(tmp_path, "test_mod", models_code=code)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_missing_ondelete(ctx)
    assert diags == []


def test_missing_ondelete_skips_non_m2o(tmp_path):
    from odoo_doctor.rules.data_integrity.missing_ondelete import check_missing_ondelete

    code = dedent("""\
        from odoo import models, fields

        class MyModel(models.Model):
            _name = "my.model"
            name = fields.Char()
            tag_ids = fields.Many2many("res.partner.category")
    """)
    _make_addon(tmp_path, "test_mod", models_code=code)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_missing_ondelete(ctx)
    assert diags == []


# --- data-noupdate-risk tests ---


def test_data_noupdate_risk_flags_critical_without_noupdate(tmp_path):
    from odoo_doctor.rules.data_integrity.data_noupdate_risk import (
        check_data_noupdate_risk,
    )

    xml = dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <odoo>
            <record id="my_rule" model="ir.rule">
                <field name="name">My Rule</field>
                <field name="model_id" ref="model_res_partner"/>
            </record>
        </odoo>
    """)
    _make_addon(tmp_path, "test_mod", xml_data=xml)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_data_noupdate_risk(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "data-noupdate-risk"


def test_data_noupdate_risk_clean_with_noupdate(tmp_path):
    from odoo_doctor.rules.data_integrity.data_noupdate_risk import (
        check_data_noupdate_risk,
    )

    xml = dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <odoo>
            <data noupdate="1">
                <record id="my_rule" model="ir.rule">
                    <field name="name">My Rule</field>
                    <field name="model_id" ref="model_res_partner"/>
                </record>
            </data>
        </odoo>
    """)
    _make_addon(tmp_path, "test_mod", xml_data=xml)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_data_noupdate_risk(ctx)
    assert diags == []


def test_data_noupdate_risk_ignores_non_critical(tmp_path):
    from odoo_doctor.rules.data_integrity.data_noupdate_risk import (
        check_data_noupdate_risk,
    )

    xml = dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <odoo>
            <record id="my_view" model="ir.ui.view">
                <field name="name">My View</field>
            </record>
        </odoo>
    """)
    _make_addon(tmp_path, "test_mod", xml_data=xml)
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_data_noupdate_risk(ctx)
    assert diags == []
