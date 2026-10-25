"""csrf-disabled-authenticated-route: session-authenticated, state-changing, no CSRF token."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.security.csrf_disabled_authenticated_route import (
    check_csrf_disabled_authenticated_route,
)


def _check(tmp_path: Path, route: str, where="controllers/main.py"):
    path = tmp_path / "mod" / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from odoo import http\n\n\nclass C(http.Controller):\n"
        f"    @http.route({route})\n    def handler(self, **kw):\n        return 'ok'\n"
    )
    return check_csrf_disabled_authenticated_route(path, "mod", "17.0")


def test_user_post_route_without_csrf_is_flagged_high(tmp_path: Path):
    diags = _check(
        tmp_path, "'/my/save', type='http', auth='user', methods=['POST'], csrf=False"
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "csrf-disabled-authenticated-route",
        "P1",
        "Security",
        "high",
    )
    assert d.line == 5
    assert "csrf_token" in d.help


def test_defaults_are_user_and_http(tmp_path: Path):
    diags = _check(tmp_path, "'/my/save', csrf=False")
    assert [d.confidence for d in diags] == ["medium"]  # methods not restricted


@pytest.mark.parametrize(
    "route",
    [
        "'/w', type='http', auth='public', methods=['POST'], csrf=False",
        "'/w', type='http', auth='none', methods=['POST'], csrf=False",
        "'/w', type='json', auth='user', methods=['POST'], csrf=False",
        "'/w', type='jsonrpc', auth='user', csrf=False",
        "'/w', type='http', auth='user', methods=['GET'], csrf=False",
        "'/w', type='http', auth='user', methods=['GET', 'HEAD'], csrf=False",
        "'/w', type='http', auth='user', methods=['POST']",
        "'/w', type='http', auth='user', methods=['POST'], csrf=True",
        "'/w', type='http', auth=AUTH, methods=['POST'], csrf=False",
        "'/w', type='http', auth='user', methods=METHODS, csrf=False",
    ],
)
def test_routes_that_are_safe_or_undecidable_are_not_flagged(
    tmp_path: Path, route: str
):
    assert _check(tmp_path, route) == []


def test_methods_mixing_get_and_post_is_flagged(tmp_path: Path):
    diags = _check(tmp_path, "'/w', auth='user', methods=['GET', 'POST'], csrf=False")
    assert [d.confidence for d in diags] == ["high"]


def test_route_imported_directly_is_found(tmp_path: Path):
    path = tmp_path / "mod" / "controllers" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from odoo.http import route, Controller\n\n\nclass C(Controller):\n"
        "    @route('/x', methods=['PUT'], csrf=False)\n    def h(self):\n        pass\n"
    )
    assert len(check_csrf_disabled_authenticated_route(path, "mod", "17.0")) == 1


def test_tests_are_skipped(tmp_path: Path):
    assert (
        _check(
            tmp_path, "'/w', auth='user', methods=['POST'], csrf=False", "tests/t.py"
        )
        == []
    )


def _file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "mod" / "controllers" / "main.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from odoo import http\n\n\n" + body)
    return path


def test_bare_override_takes_the_auth_of_the_route_it_overrides(tmp_path: Path):
    path = _file(
        tmp_path,
        "class Base(http.Controller):\n"
        "    @http.route('/h', auth='public', methods=['POST'])\n"
        "    def h(self):\n        pass\n\n\n"
        "class Over(Base):\n"
        "    @http.route(methods=['POST'], csrf=False)\n"
        "    def h(self):\n        pass\n",
    )
    assert check_csrf_disabled_authenticated_route(path, "mod", "17.0") == []


def test_override_of_an_unscanned_parent_is_not_flagged(tmp_path: Path):
    path = _file(
        tmp_path,
        "class Over(OtherController):\n"
        "    @http.route(methods=['POST'], csrf=False)\n"
        "    def h(self):\n        pass\n",
    )
    assert check_csrf_disabled_authenticated_route(path, "mod", "17.0") == []


def test_override_of_a_user_route_is_flagged(tmp_path: Path):
    path = _file(
        tmp_path,
        "class Base(http.Controller):\n"
        "    @http.route('/h', auth='user')\n"
        "    def h(self):\n        pass\n\n\n"
        "class Over(Base):\n"
        "    @http.route(methods=['POST'], csrf=False)\n"
        "    def h(self):\n        pass\n",
    )
    assert len(check_csrf_disabled_authenticated_route(path, "mod", "17.0")) == 1
