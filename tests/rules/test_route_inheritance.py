"""Route inheritance: an override that omits ``auth`` keeps the parent route's."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

import odoo_doctor.cli.app  # noqa: F401  (registers the rules)
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.parsers.python_models import parse_controllers
from odoo_doctor.rules.security.public_controller_sudo import (
    check_public_controller_sudo_in_module,
)
from odoo_doctor.rules.security.rpc_sudo_without_access_check import (
    check_rpc_sudo_in_module,
    check_rpc_sudo_without_access_check,
)

HEAD = "from odoo import http\nfrom odoo.http import request\n\n\n"
BASE = """\
class Base(http.Controller):
    @http.route("/p", auth="public")
    def pub(self):
        return 1

    @http.route("/u", auth="user")
    def priv(self):
        return 1
"""


def _auth(tmp_path: Path, code: str) -> dict[str, str]:
    f = tmp_path / "c.py"
    f.write_text(HEAD + dedent(code))
    return {c.method_name: c.auth for c in parse_controllers(f)}


def test_a_route_without_a_parent_runs_as_user(tmp_path: Path):
    auth = _auth(
        tmp_path,
        """\
        class A(http.Controller):
            @http.route("/a")
            def a(self): ...
        """,
    )
    assert auth == {"a": "user"}


@pytest.mark.parametrize("route", ["@http.route()", '@http.route("/n", website=True)'])
def test_an_override_keeps_the_public_auth_of_its_parent(tmp_path: Path, route: str):
    auth = _auth(
        tmp_path,
        BASE + f"\n\nclass Child(Base):\n    {route}\n    def pub(self): ...\n",
    )
    assert auth["pub"] == "public"  # Child.pub (the dict keeps the last of two)


def test_inheritance_runs_through_several_levels_and_an_explicit_auth_wins(
    tmp_path: Path,
):
    code = (
        BASE
        + """

class Child(Base):
    @http.route()
    def pub(self): ...

    @http.route()
    def priv(self): ...


class Grand(Child):
    @http.route()
    def pub(self): ...

    @http.route("/u", auth="public")
    def priv(self): ...
"""
    )
    f = tmp_path / "c.py"
    f.write_text(HEAD + code)
    got = [(c.method_name, c.auth) for c in parse_controllers(f)]
    assert got == [
        ("pub", "public"),
        ("priv", "user"),
        ("pub", "public"),
        ("priv", "user"),
        ("pub", "public"),
        ("priv", "public"),
    ]


def test_a_parent_outside_the_code_leaves_the_auth_unknown(tmp_path: Path):
    auth = _auth(
        tmp_path,
        """\
        from odoo.addons.website_sale.controllers.main import WebsiteSale

        class Shop(WebsiteSale):
            @http.route()
            def shop(self): ...

            @http.route("/s", auth="user")
            def other(self): ...
        """,
    )
    assert auth == {"shop": "unknown", "other": "user"}


def test_a_computed_auth_is_unknown(tmp_path: Path):
    auth = _auth(
        tmp_path,
        """\
        AUTH = "public"

        class A(http.Controller):
            @http.route("/a", auth=AUTH)
            def a(self): ...
        """,
    )
    assert auth == {"a": "unknown"}


def test_a_cycle_of_same_named_classes_does_not_loop(tmp_path: Path):
    auth = _auth(
        tmp_path,
        """\
        class Home(Home):
            @http.route()
            def index(self): ...
        """,
    )
    assert auth == {"index": "unknown"}


def _two_addons(tmp_path: Path, base_code: str, child_code: str):
    for name, code, depends in (
        ("base_mod", base_code, []),
        ("child", child_code, ["base_mod"]),
    ):
        addon = tmp_path / name
        (addon / "controllers").mkdir(parents=True)
        (addon / "__manifest__.py").write_text(
            repr(
                {"name": name, "version": "19.0.1.0.0", "depends": depends, "data": []}
            )
        )
        (addon / "controllers" / "main.py").write_text(HEAD + dedent(code))
    return build_project_graph([tmp_path], odoo_version="19.0").modules


def test_the_parent_is_found_in_another_addon(tmp_path: Path):
    modules = _two_addons(
        tmp_path,
        BASE,
        """\
        from odoo.addons.base_mod.controllers.main import Base

        class Child(Base):
            @http.route()
            def pub(self):
                return request.env["x"].sudo().browse(1).name
        """,
    )
    (ctrl,) = modules["child"].controllers
    assert ctrl.auth == "public"
    (diag,) = check_public_controller_sudo_in_module(modules["child"])
    assert diag.confidence == "medium"  # inherited, not written on the route
    assert "inherits auth='public'" in diag.message


def test_an_unresolved_parent_is_reported_one_grade_lower(tmp_path: Path):
    modules = _two_addons(
        tmp_path,
        BASE,
        """\
        from odoo.addons.website_sale.controllers.main import WebsiteSale

        class Shop(WebsiteSale):
            @http.route()
            def shop(self):
                return request.env["x"].sudo().browse(1).name
        """,
    )
    (diag,) = check_public_controller_sudo_in_module(modules["child"])
    assert diag.confidence == "medium"
    assert "not in the scanned code" in diag.message


def test_an_authenticated_parent_is_not_a_public_route(tmp_path: Path):
    modules = _two_addons(
        tmp_path,
        BASE,
        """\
        from odoo.addons.base_mod.controllers.main import Base

        class Child(Base):
            @http.route()
            def priv(self):
                return request.env["x"].sudo().browse(1).name
        """,
    )
    assert check_public_controller_sudo_in_module(modules["child"]) == []


CLOSE = """\
    @http.route("/c/<int:rec_id>", auth="user")
    def close(self, rec_id):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})
"""


@pytest.mark.parametrize(
    "bases", ["CustomerPortal", "portal.CustomerPortal", "Base", "Base, Mixin"]
)
def test_rpc_sudo_sees_controllers_whatever_their_base_is_called(
    tmp_path: Path, bases: str
):
    f = tmp_path / "c.py"
    f.write_text(HEAD + f"class Portal({bases}):\n" + CLOSE)
    (diag,) = check_rpc_sudo_without_access_check(f, "m", "19.0")
    assert diag.rule == "rpc-sudo-without-access-check" and diag.confidence == "high"


def test_rpc_sudo_skips_a_route_whose_inherited_auth_may_be_public(tmp_path: Path):
    modules = _two_addons(
        tmp_path,
        BASE,
        """\
        from odoo.addons.base_mod.controllers.main import Base

        class Child(Base):
            @http.route()
            def pub(self, rec_id=0):
                request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})

            @http.route()
            def priv(self, rec_id=0):
                request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})
        """,
    )
    diags = check_rpc_sudo_in_module(modules["child"])
    (priv,) = (c for c in modules["child"].controllers if c.method_name == "priv")
    assert [d.line for d in diags] == [priv.line + 1]  # the sudo() line of priv


def test_a_written_auth_stays_high_and_an_inherited_one_is_graded_lower(tmp_path: Path):
    modules = _two_addons(
        tmp_path,
        BASE,
        """\
        from odoo.addons.base_mod.controllers.main import Base

        class Child(Base):
            @http.route("/w", auth="public")
            def written(self):
                return request.env["x"].sudo().browse(1).name

            @http.route()
            def pub(self):
                return request.env["x"].sudo().browse(1).name
        """,
    )
    diags = check_public_controller_sudo_in_module(modules["child"])
    assert sorted(d.confidence for d in diags) == ["high", "medium"]
