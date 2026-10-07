"""public-controller-sudo-risk: elevation on a public route, graded by access checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent, indent

from odoo_doctor.parsers.python_models import parse_controllers
from odoo_doctor.rules.security.public_controller_sudo import (
    check_public_controller_sudo,
)


def _scan(tmp_path: Path, body: str, auth: str = "public"):
    header = (
        "from odoo import http\n"
        "from odoo.tools import consteq\n\n"
        "class C(http.Controller):\n"
        f'    @http.route("/x", auth="{auth}")\n'
        "    def handler(self, order_id=None, access_token=None):\n"
    )
    f = tmp_path / "c.py"
    f.write_text(header + indent(dedent(body), " " * 8))
    return check_public_controller_sudo(f, "m", "19.0"), f


def test_unguarded_elevation_is_high_confidence(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        return http.request.env["sale.order"].sudo().browse(order_id).read()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]


def test_document_check_access_before_sudo_is_a_guard(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        order = self._document_check_access("sale.order", order_id, access_token)
        return order.sudo().read()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]
    assert "access check" in diags[0].message


def test_constant_time_token_comparison_is_a_guard(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        order = http.request.env["sale.order"].sudo().browse(order_id)
        if not consteq(order.access_token, access_token):
            raise http.request.not_found()
        return order.read()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_generating_a_token_is_not_a_guard(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        order = http.request.env["sale.order"].sudo().browse(order_id)
        return order._portal_ensure_token()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]


def test_sudo_false_is_not_an_elevation(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        return http.request.env["sale.order"].sudo(False).search([])
        """,
    )
    assert diags == []


def test_reading_a_constant_config_parameter_is_not_reported(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        return http.request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        """,
    )
    assert diags == []


def test_config_parameter_with_a_request_controlled_key_is_reported(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        return http.request.env["ir.config_parameter"].sudo().get_param(access_token)
        """,
    )
    assert len(diags) == 1


def test_config_parameter_next_to_another_elevation_is_reported(tmp_path: Path):
    diags, _ = _scan(
        tmp_path,
        """\
        base = http.request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return http.request.env["res.users"].sudo().search([]), base
        """,
    )
    assert len(diags) == 1


def test_parser_exposes_the_guard(tmp_path: Path):
    _, f = _scan(
        tmp_path,
        """\
        order = self._document_check_access("sale.order", order_id, access_token)
        return order.sudo().read()
        """,
    )
    (ctrl,) = parse_controllers(f)
    assert ctrl.uses_sudo is True and ctrl.guarded is True
