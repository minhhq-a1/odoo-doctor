"""Multi-company / multi-currency rules (0.6.0)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.correctness.hardcoded_company_or_currency import (
    check_hardcoded_company_or_currency,
)
from odoo_doctor.rules.correctness.monetary_missing_currency_field import (
    check_monetary_missing_currency_field,
)
from odoo_doctor.rules.security.missing_multicompany_rule import (
    check_missing_multicompany_rule,
)


def _addon(
    root: Path,
    name: str,
    files: dict[str, str],
    *,
    depends: list[str] | None = None,
    data: list[str] | None = None,
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
    for rel, content in files.items():
        target = mod / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content))
    return mod


def _ctx(root: Path, name: str):
    return build_project_graph([root], odoo_version="17.0").modules[name]


# --- monetary-missing-currency-field ------------------------------------------


def _monetary(tmp_path: Path, body: str):
    """Build addon `mod` with one model `mod.invoice` whose fields are `body`."""
    fields_code = "\n".join("    " + line for line in dedent(body).strip().splitlines())
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": "from odoo import fields, models\n\n\n"
            "class Invoice(models.Model):\n"
            '    _name = "mod.invoice"\n'
            '    _description = "Invoice"\n' + fields_code + "\n"
        },
    )
    return check_monetary_missing_currency_field(_ctx(tmp_path, "mod"))


def test_monetary_without_any_currency_field_is_flagged(tmp_path: Path):
    diags = _monetary(tmp_path, 'amount = fields.Monetary(string="Amount")')
    assert len(diags) == 1
    assert diags[0].rule == "monetary-missing-currency-field"
    assert diags[0].confidence == "high"
    assert "amount" in diags[0].message


def test_monetary_with_currency_id_is_fine(tmp_path: Path):
    body = """\
        currency_id = fields.Many2one("res.currency")
        amount = fields.Monetary()
        """
    assert _monetary(tmp_path, body) == []


def test_monetary_with_explicit_existing_currency_field_is_fine(tmp_path: Path):
    body = """\
        company_currency_id = fields.Many2one("res.currency")
        amount = fields.Monetary(currency_field="company_currency_id")
        """
    assert _monetary(tmp_path, body) == []


def test_monetary_pointing_at_missing_currency_field_is_flagged(tmp_path: Path):
    body = """\
        currency_id = fields.Many2one("res.currency")
        amount = fields.Monetary(currency_field="nope_currency_id")
        """
    diags = _monetary(tmp_path, body)
    assert len(diags) == 1
    assert "nope_currency_id" in diags[0].message


def test_monetary_currency_inherited_from_parent_model_is_fine(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Base(models.Model):
                _name = "mod.base"
                _description = "Base"
                currency_id = fields.Many2one("res.currency")

            class Child(models.Model):
                _inherit = "mod.base"
                _name = "mod.child"
                _description = "Child"
                amount = fields.Monetary()
            """
        },
    )
    assert check_monetary_missing_currency_field(_ctx(tmp_path, "mod")) == []


def test_monetary_added_by_extension_of_external_model_is_not_flagged(tmp_path: Path):
    # sale.order is not defined in this repo: its currency_id is unknowable here.
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class SaleOrder(models.Model):
                _inherit = "sale.order"
                x_fee = fields.Monetary()
            """
        },
        depends=["base", "sale"],
    )
    assert check_monetary_missing_currency_field(_ctx(tmp_path, "mod")) == []


def test_monetary_currency_added_by_extension_in_another_module_is_fine(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Invoice(models.Model):
                _name = "mod.invoice"
                _description = "Invoice"
                amount = fields.Monetary()
            """
        },
    )
    _addon(
        tmp_path,
        "ext",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Invoice(models.Model):
                _inherit = "mod.invoice"
                currency_id = fields.Many2one("res.currency")
            """
        },
        depends=["mod"],
    )
    assert check_monetary_missing_currency_field(_ctx(tmp_path, "mod")) == []


# --- missing-multicompany-rule ------------------------------------------------

_COMPANY_MODEL = """\
    from odoo import fields, models

    class Thing(models.Model):
        _name = "mod.thing"
        _description = "Thing"
        company_id = fields.Many2one("res.company", required=True)
"""

_RULE_XML = """\
    <odoo>
      <record id="thing_comp_rule" model="ir.rule">
        <field name="name">thing multi-company</field>
        <field name="model_id" ref="model_mod_thing"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
      </record>
    </odoo>
"""


def test_company_model_without_record_rule_is_flagged_medium(tmp_path: Path):
    _addon(tmp_path, "mod", {"models/m.py": _COMPANY_MODEL})
    diags = check_missing_multicompany_rule(_ctx(tmp_path, "mod"))
    assert len(diags) == 1
    assert diags[0].rule == "missing-multicompany-rule"
    assert diags[0].confidence == "medium"
    assert "mod.thing" in diags[0].message


def test_company_model_with_record_rule_is_fine(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {"models/m.py": _COMPANY_MODEL, "security/rule.xml": _RULE_XML},
        data=["security/rule.xml"],
    )
    assert check_missing_multicompany_rule(_ctx(tmp_path, "mod")) == []


def test_record_rule_in_another_module_counts(tmp_path: Path):
    _addon(tmp_path, "mod", {"models/m.py": _COMPANY_MODEL})
    _addon(
        tmp_path,
        "rules",
        {
            "security/rule.xml": _RULE_XML.replace(
                'ref="model_mod_thing"', 'ref="mod.model_mod_thing"'
            )
        },
        depends=["mod"],
        data=["security/rule.xml"],
    )
    assert check_missing_multicompany_rule(_ctx(tmp_path, "mod")) == []


def test_model_without_company_field_is_not_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Thing(models.Model):
                _name = "mod.thing"
                _description = "Thing"
                name = fields.Char()
            """
        },
    )
    assert check_missing_multicompany_rule(_ctx(tmp_path, "mod")) == []


def test_company_id_pointing_elsewhere_is_not_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Thing(models.Model):
                _name = "mod.thing"
                _description = "Thing"
                company_id = fields.Many2one("res.partner")
            """
        },
    )
    assert check_missing_multicompany_rule(_ctx(tmp_path, "mod")) == []


def test_transient_and_abstract_models_are_not_flagged(tmp_path: Path):
    _addon(
        tmp_path,
        "mod",
        {
            "models/m.py": """\
            from odoo import fields, models

            class Wiz(models.TransientModel):
                _name = "mod.wiz"
                _description = "Wiz"
                company_id = fields.Many2one("res.company")

            class Mixin(models.AbstractModel):
                _name = "mod.mixin"
                _description = "Mixin"
                company_id = fields.Many2one("res.company")
            """
        },
    )
    assert check_missing_multicompany_rule(_ctx(tmp_path, "mod")) == []


# --- hardcoded-company-or-currency --------------------------------------------


def _hardcoded(
    tmp_path: Path, code: str, rel: str = "models/m.py", module: str = "mod"
):
    f = tmp_path / module / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(code))
    return check_hardcoded_company_or_currency(f, module, "17.0")


def test_main_company_reference_is_flagged(tmp_path: Path):
    diags = _hardcoded(
        tmp_path,
        """\
        def run(self):
            return self.env.ref("base.main_company")
        """,
    )
    assert len(diags) == 1
    assert diags[0].rule == "hardcoded-company-or-currency"
    assert diags[0].confidence == "medium"
    assert "main_company" in diags[0].message


def test_hardcoded_currency_reference_is_flagged(tmp_path: Path):
    diags = _hardcoded(
        tmp_path,
        """\
        def run(self):
            return self.env.ref("base.USD")
        """,
    )
    assert len(diags) == 1
    assert "USD" in diags[0].message


def test_other_references_are_not_flagged(tmp_path: Path):
    assert (
        _hardcoded(
            tmp_path,
            """\
            def run(self):
                self.env.ref("base.group_user")
                self.env.ref("mod.USD")
                return self.env.company
            """,
        )
        == []
    )


def test_install_hooks_are_not_flagged(tmp_path: Path):
    assert (
        _hardcoded(
            tmp_path,
            """\
            def post_init_hook(env):
                env.ref("base.main_company").write({"name": "x"})
            """,
            rel="hooks.py",
        )
        == []
    )


def test_migrations_and_tests_are_not_flagged(tmp_path: Path):
    code = """\
    def run(self):
        return self.env.ref("base.main_company")
    """
    assert _hardcoded(tmp_path, code, rel="migrations/17.0.1.0/post.py") == []
    assert _hardcoded(tmp_path, code, rel="tests/test_x.py") == []
