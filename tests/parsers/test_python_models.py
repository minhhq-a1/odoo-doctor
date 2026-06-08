# tests/parsers/test_python_models.py
"""Tests for Python model/controller parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.python_models import (
    parse_controllers,
    parse_models,
)


def test_parse_inherit_model(sample_addon: Path):
    models = parse_models(sample_addon / "models" / "sale_custom.py")
    assert len(models) == 2

    sale = next(m for m in models if "sale.order" in m.inherit)
    assert "custom_note" in sale.fields
    assert sale.fields["custom_note"].field_type == "Text"
    assert "total_weight" in sale.fields
    assert sale.fields["total_weight"].compute == "_compute_total_weight"

    assert "_compute_total_weight" in sale.methods
    assert sale.methods["_compute_total_weight"].depends == ["order_line.product_id"]
    assert "action_confirm_custom" in sale.methods


def test_parse_new_model(sample_addon: Path):
    models = parse_models(sample_addon / "models" / "sale_custom.py")
    wizard = next(m for m in models if m.name == "sale.custom.wizard")
    assert wizard.is_transient is True
    assert "name" in wizard.fields


def test_parse_controller(tmp_path: Path):
    code = dedent("""\
        from odoo import http

        class MyController(http.Controller):
            @http.route("/api/data", auth="public", type="json")
            def get_data(self):
                records = http.request.env["res.partner"].sudo().search([])
                return records.read(["name"])
    """)
    f = tmp_path / "controller.py"
    f.write_text(code)
    controllers = parse_controllers(f)
    assert len(controllers) == 1
    assert controllers[0].route == "/api/data"
    assert controllers[0].auth == "public"
    assert controllers[0].uses_sudo is True


def test_parse_empty_file(tmp_path: Path):
    f = tmp_path / "empty.py"
    f.write_text("")
    assert parse_models(f) == []
    assert parse_controllers(f) == []


def test_parse_models_tolerates_non_utf8(tmp_path):
    f = tmp_path / "latin1.py"
    # 0xE9 ('é' in latin-1) makes strict-UTF-8 read_text() raise UnicodeDecodeError
    f.write_bytes(b"# -*- coding: latin-1 -*-\nNAME = '\xe9'\n")
    # Must not raise; no Odoo model defined → empty list
    assert parse_models(f) == []


def test_parse_controllers_tolerates_non_utf8(tmp_path):
    f = tmp_path / "latin1_ctrl.py"
    f.write_bytes(b"# -*- coding: latin-1 -*-\nNAME = '\xe9'\n")
    assert parse_controllers(f) == []
