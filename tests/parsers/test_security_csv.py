# tests/parsers/test_security_csv.py
"""Tests for security CSV parser."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.parsers.security_csv import parse_access_csv


def test_parse_access_csv(sample_addon: Path):
    csv_file = sample_addon / "security" / "ir.model.access.csv"
    rules = parse_access_csv(csv_file, module_name="sample_addon")
    assert len(rules) == 1
    r = rules[0]
    assert r.id == "access_sale_custom_wizard_user"
    assert r.model_external_id == "model_sale_custom_wizard"
    assert r.model_external_id_module == "sample_addon"
    assert r.group_id == "base.group_user"
    assert r.perm_read is True


def test_parse_access_csv_model_name_extraction():
    """model_sale_custom_wizard -> sale.custom.wizard"""
    from odoo_doctor.parsers.security_csv import model_external_id_to_name

    assert model_external_id_to_name("model_sale_custom_wizard") == "sale.custom.wizard"
    assert model_external_id_to_name("model_res_partner") == "res.partner"


def test_parse_empty_csv(tmp_path: Path):
    f = tmp_path / "ir.model.access.csv"
    f.write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
    )
    assert parse_access_csv(f, module_name="m") == []


def test_parse_missing_file(tmp_path: Path):
    assert parse_access_csv(tmp_path / "missing.csv", module_name="m") == []
