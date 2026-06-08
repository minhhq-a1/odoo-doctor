# tests/graph/test_resolver.py
"""Tests for stub loading and confidence-aware symbol resolver."""

from __future__ import annotations

from odoo_doctor.graph.stubs.loader import load_stubs
from odoo_doctor.graph.resolver import ResolveResult, SymbolResolver
from odoo_doctor.parsers.python_models import FieldInfo, ModelInfo


def test_load_stubs_17():
    stubs = load_stubs("17.0")
    assert stubs is not None
    assert "res.partner" in stubs.models
    assert "name" in stubs.models["res.partner"]["fields"]
    assert "base.main_company" in stubs.xml_ids


def test_load_stubs_unknown_version():
    stubs = load_stubs("99.0")
    assert stubs is None


# --- Resolver tests ---


def _make_resolver(repo_models=None, stub_version="17.0", source_path=None):
    return SymbolResolver(
        repo_models=repo_models or {},
        repo_xml_ids={},
        stub_version=stub_version,
        source_path=source_path,
    )


def test_resolve_field_from_repo():
    models = {
        "sale.custom": ModelInfo(
            name="sale.custom",
            file_path="f.py",
            line=1,
            fields={"my_field": FieldInfo(name="my_field", field_type="Char")},
        )
    }
    r = _make_resolver(repo_models=models)
    result = r.resolve_field("sale.custom", "my_field")
    assert result.status == ResolveResult.FOUND
    assert result.source == "repo"


def test_resolve_field_from_stub():
    r = _make_resolver()
    result = r.resolve_field("res.partner", "name")
    assert result.status == ResolveResult.FOUND
    assert result.source == "stub"


def test_resolve_field_partial_stub_is_unknown():
    """Field absent from a PARTIAL stub model is UNKNOWN, never NOT_FOUND (golden rule)."""
    r = _make_resolver()
    result = r.resolve_field("res.partner", "zzz_nonexistent_field")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_field_repo_model_provable_not_found():
    """A repo-defined model with no _inherit has fully-known fields -> absence provable."""
    models = {
        "my.model": ModelInfo(
            name="my.model",
            file_path="f.py",
            line=1,
            fields={"foo": FieldInfo(name="foo", field_type="Char")},
        )
    }
    r = _make_resolver(repo_models=models)
    assert r.resolve_field("my.model", "foo").status == ResolveResult.FOUND
    assert r.resolve_field("my.model", "bar").status == ResolveResult.NOT_FOUND


def test_resolve_field_repo_model_inheriting_core_is_unknown():
    """Repo model that _inherits a partial-stub core model cannot prove absence."""
    models = {
        "my.order": ModelInfo(
            name="my.order",
            file_path="f.py",
            line=1,
            inherit=["sale.order"],
            fields={"foo": FieldInfo(name="foo", field_type="Char")},
        )
    }
    r = _make_resolver(repo_models=models)
    assert r.resolve_field("my.order", "foo").status == ResolveResult.FOUND
    assert r.resolve_field("my.order", "bar").status == ResolveResult.UNKNOWN


def test_resolve_field_magic_field_always_found():
    r = _make_resolver()
    for f in ("id", "create_uid", "write_date", "display_name"):
        res = r.resolve_field("sale.order", f)
        assert res.status == ResolveResult.FOUND, f


def test_resolve_field_unknown_model():
    """Model not in repo or stubs -> UNKNOWN, not NOT_FOUND."""
    r = _make_resolver()
    result = r.resolve_field("totally.unknown.model", "any_field")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_model_found_in_stub():
    r = _make_resolver()
    result = r.resolve_model("sale.order")
    assert result.status == ResolveResult.FOUND


def test_resolve_model_unknown():
    r = _make_resolver()
    result = r.resolve_model("zzz.nonexistent")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_method_found():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "action_confirm")
    assert result.status == ResolveResult.FOUND


def test_resolve_method_partial_stub_is_unknown():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "zzz_method")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_xml_id_found():
    r = _make_resolver()
    result = r.resolve_xml_id("base.main_company")
    assert result.status == ResolveResult.FOUND


def test_resolve_xml_id_unknown():
    r = _make_resolver()
    result = r.resolve_xml_id("nonexistent.xml_id")
    assert result.status == ResolveResult.UNKNOWN


def test_golden_rule_unknown_is_not_not_found():
    """The golden rule: UNKNOWN must never be treated as NOT_FOUND."""
    r = _make_resolver()
    field_result = r.resolve_field("unknown.model", "any_field")
    assert field_result.status != ResolveResult.NOT_FOUND
    assert field_result.status == ResolveResult.UNKNOWN


def test_stubs_cover_spec_required_modules():
    """Spec requires stubs for: base, web, mail, contacts, product, sale, purchase, stock, account."""
    stubs = load_stubs("17.0")
    assert stubs is not None

    # base models
    assert "res.partner" in stubs.models
    assert "res.users" in stubs.models
    assert "res.company" in stubs.models
    assert "res.groups" in stubs.models
    assert "res.config.settings" in stubs.models
    assert "ir.model" in stubs.models
    assert "ir.model.fields" in stubs.models
    assert "ir.model.access" in stubs.models
    assert "ir.rule" in stubs.models
    assert "ir.actions.act_window" in stubs.models
    assert "ir.cron" in stubs.models
    assert "ir.sequence" in stubs.models
    assert "ir.attachment" in stubs.models
    assert "ir.ui.view" in stubs.models

    # web
    assert "ir.http" in stubs.models

    # mail
    assert "mail.thread" in stubs.models
    assert "mail.message" in stubs.models
    assert "mail.activity.mixin" in stubs.models
    assert "mail.followers" in stubs.models

    # contacts (res.partner already covered above)

    # product
    assert "product.product" in stubs.models
    assert "product.template" in stubs.models
    assert "product.category" in stubs.models

    # sale
    assert "sale.order" in stubs.models
    assert "sale.order.line" in stubs.models

    # purchase
    assert "purchase.order" in stubs.models
    assert "purchase.order.line" in stubs.models

    # stock
    assert "stock.picking" in stubs.models
    assert "stock.move" in stubs.models
    assert "stock.warehouse" in stubs.models
    assert "stock.location" in stubs.models

    # account
    assert "account.move" in stubs.models
    assert "account.move.line" in stubs.models
    assert "account.journal" in stubs.models
    assert "account.account" in stubs.models


def test_resolve_xml_id_for_module():
    r = SymbolResolver(
        repo_models={},
        repo_xml_ids={"sale_custom.my_record": object()},
        stub_version="17.0",
    )
    # Found in repo
    res1 = r.resolve_xml_id_for_module("sale_custom.my_record", "sale_custom")
    assert res1.status == ResolveResult.FOUND

    # Local unknown -> LOCAL_NOT_FOUND (no dot)
    res2 = r.resolve_xml_id_for_module("my_missing_record", "sale_custom")
    assert res2.status == ResolveResult.LOCAL_NOT_FOUND

    # Local unknown -> LOCAL_NOT_FOUND (with dot matching current module)
    res3 = r.resolve_xml_id_for_module("sale_custom.my_missing_record", "sale_custom")
    assert res3.status == ResolveResult.LOCAL_NOT_FOUND

    # External unknown -> UNKNOWN
    res4 = r.resolve_xml_id_for_module("other_module.my_missing_record", "sale_custom")
    assert res4.status == ResolveResult.UNKNOWN


def test_owner_module_for_model():
    repo_models = {
        "custom.model": ModelInfo(
            name="custom.model",
            file_path="custom_addon/models/custom.py",
            line=10,
            module="custom_addon",
        )
    }
    r = SymbolResolver(
        repo_models=repo_models,
        repo_xml_ids={},
        stub_version="17.0",
    )
    # 1. Repo owned model
    lookup1 = r.owner_module_for_model("custom.model")
    assert lookup1.status == ResolveResult.FOUND
    assert lookup1.source == "custom_addon"

    # 2. Overrides owned model
    lookup2 = r.owner_module_for_model("sale.order")
    assert lookup2.status == ResolveResult.FOUND
    assert lookup2.source == "sale"

    # 3. Unknown model owner
    lookup3 = r.owner_module_for_model("unknown.model")
    assert lookup3.status == ResolveResult.UNKNOWN


def test_magic_fields_constant_exists():
    from odoo_doctor.graph.resolver import ORM_MAGIC_FIELDS

    for f in (
        "id",
        "display_name",
        "create_uid",
        "create_date",
        "write_uid",
        "write_date",
        "__last_update",
    ):
        assert f in ORM_MAGIC_FIELDS


def test_resolver_accepts_extended_methods_param():
    from odoo_doctor.parsers.python_models import MethodInfo

    r = SymbolResolver(
        repo_models={},
        repo_xml_ids={},
        stub_version="17.0",
        extended_methods={"sale.order": {"action_foo": MethodInfo(name="action_foo")}},
    )
    # Stored and queryable; resolve_method behavior is verified in Task 4.
    assert r._extended_methods["sale.order"]["action_foo"].name == "action_foo"


def test_resolve_method_extended_via_inherit_found():
    from odoo_doctor.parsers.python_models import MethodInfo

    r = SymbolResolver(
        repo_models={},
        repo_xml_ids={},
        stub_version="17.0",
        extended_methods={"sale.order": {"action_foo": MethodInfo(name="action_foo")}},
    )
    assert r.resolve_method("sale.order", "action_foo").status == ResolveResult.FOUND
