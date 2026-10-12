"""rpc-sudo-without-access-check: a public method elevates privileges on what the caller picked."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from odoo_doctor.rules.security.rpc_sudo_without_access_check import (
    check_rpc_sudo_without_access_check,
)

MODEL = (
    "from odoo import api, models\n\n\nclass M(models.Model):\n    _name = 'x.m'\n\n"
)


def _diags(tmp_path: Path, body: str, header: str = MODEL, name: str = "m.py"):
    f = tmp_path / name
    f.write_text(header + body)
    return check_rpc_sudo_without_access_check(f, "m", "17.0")


def _indent(code: str) -> str:
    return "".join(
        "    " + line if line.strip() else line
        for line in dedent(code).splitlines(True)
    )


def _model(tmp_path: Path, code: str):
    return _diags(tmp_path, _indent(code))


@pytest.mark.parametrize(
    "code",
    [
        """\
        def remove(self, rid):
            return self.env['x.y'].sudo().browse(rid).unlink()
        """,
        """\
        def remove(self, rid):
            return self.env['x.y'].browse(rid).sudo().unlink()
        """,
        """\
        def remove(self, rid):
            records = self.env['x.y'].sudo()
            return records.browse(rid).write({'a': 1})
        """,
        """\
        def make(self, vals):
            return self.env['x.y'].sudo().create(vals)
        """,
        """\
        def close(self, rid):
            rec = self.env['x.y'].browse(rid)
            rec.sudo().write({'state': 'closed'})
        """,
        """\
        def save(self, vals):
            return self.sudo().write(vals)
        """,
    ],
    ids=[
        "chain",
        "browse-then-sudo",
        "sudo-variable",
        "search",
        "var-then-sudo",
        "self-write",
    ],
)
def test_a_parameter_reaching_an_elevated_mutation_is_high(tmp_path: Path, code):
    diags = _model(tmp_path, code)
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "rpc-sudo-without-access-check",
        "P1",
        "Security",
        "high",
    )


def test_a_parameter_used_apart_from_the_elevation_is_medium(tmp_path: Path):
    diags = _model(
        tmp_path,
        """\
        def stats(self, rid):
            total = self.env['x.y'].sudo().search_count([])
            return total, self.env['x.z'].browse(rid).name
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


@pytest.mark.parametrize(
    "code",
    [
        # no parameter reaches the ORM
        "def stats(self):\n    return self.env['x.y'].sudo().search_count([])\n",
        "def act(self):\n    return self.sudo().write({'a': 1})\n",
        # private helper
        "def _get(self, rid):\n    return self.env['x.y'].sudo().browse(rid)\n",
        # access checked in the method
        "def get(self, rid):\n    rec = self.env['x.y'].browse(rid)\n    rec.check_access('read')\n    return rec.sudo().name\n",
        "def get(self, rid):\n    rec = self.env['x.y'].browse(rid)\n    rec.check_access_rights('read')\n    return rec.sudo().name\n",
        "def get(self, rid):\n    rec = self.env['x.y'].browse(rid)\n    if not rec.has_access('read'):\n        return False\n    return rec.sudo().name\n",
        "def get(self, rid, token):\n    rec = self.env['x.y'].sudo().browse(rid)\n    if not consteq(rec.access_token, token):\n        return False\n    return rec.name\n",
        "def get(self, rid):\n    if not self.env.user.has_group('base.group_system'):\n        return False\n    return self.env['x.y'].sudo().browse(rid).name\n",
        # not an elevation
        "def get(self, rid):\n    return self.env['x.y'].sudo(False).browse(rid).name\n",
        "def get(self, key):\n    return self.env['ir.config_parameter'].sudo().get_param('k.v')\n",
        # computes and ORM overrides run under the caller's own rights check
        "@api.depends('a')\ndef compute_total(self, rid):\n    self.total = self.env['x.y'].sudo().browse(rid).t\n",
        "def create(self, vals):\n    return super().create(vals).sudo()\n",
        "def write(self, vals):\n    return self.sudo().browse(vals['id']).write(vals)\n",
    ],
    ids=lambda c: c.splitlines()[0][:40],
)
def test_calls_without_the_risk_are_not_reported(tmp_path: Path, code):
    assert _model(tmp_path, code) == []


def test_a_class_that_is_not_a_model_is_skipped(tmp_path: Path):
    src = "class Helper:\n    def get(self, rid):\n        return self.env['x'].sudo().browse(rid)\n"
    assert _diags(tmp_path, src, header="") == []


def test_an_authenticated_route_is_checked_too(tmp_path: Path):
    header = (
        "from odoo import http\nfrom odoo.http import request\n\n\n"
        "class C(http.Controller):\n"
    )
    body = (
        "    @http.route('/x/<int:rid>', auth='user')\n"
        "    def view(self, rid):\n"
        "        return request.env['x.y'].sudo().browse(rid).unlink()\n"
    )
    diags = _diags(tmp_path, body, header=header)
    assert [d.confidence for d in diags] == ["high"]


def test_a_public_route_is_left_to_the_controller_rule(tmp_path: Path):
    header = "from odoo import http\nfrom odoo.http import request\n\n\nclass C(http.Controller):\n"
    body = (
        "    @http.route('/x/<int:rid>', auth='public')\n"
        "    def view(self, rid):\n"
        "        return request.env['x.y'].sudo().browse(rid).name\n"
    )
    assert _diags(tmp_path, body, header=header) == []


def test_tests_are_skipped(tmp_path: Path):
    (tmp_path / "m" / "tests").mkdir(parents=True)
    f = tmp_path / "m" / "tests" / "test_x.py"
    f.write_text(
        MODEL
        + "    def get(self, rid):\n        return self.env['x'].sudo().browse(rid)\n"
    )
    assert check_rpc_sudo_without_access_check(f, "m", "17.0") == []


@pytest.mark.parametrize(
    "code",
    [
        # the parameter goes through a helper that may do the check
        "def get(self, rid):\n    rec = self._get_checked(rid)\n    return rec.sudo().name\n",
        "def get(self, rid):\n    rec = self.env['x.y'].browse(helper(rid))\n    return rec.sudo().name\n",
        "def get(self, rid):\n    self._check_rights(rid)\n    return self.env['x.y'].sudo().browse(rid).name\n",
    ],
    ids=["assigned-helper", "module-helper", "check-helper"],
)
def test_a_parameter_handed_to_another_method_counts_as_delegated(tmp_path, code):
    assert _model(tmp_path, code) == []


@pytest.mark.parametrize(
    "code",
    [
        "def rm(self, rid):\n    return self.env['x.y'].sudo().browse(int(rid)).unlink()\n",
        "def rm(self, rid):\n    return self.env['x.y'].sudo().browse(rid).with_context(a=1).unlink()\n",
    ],
    ids=["int", "with_context"],
)
def test_plain_conversions_do_not_count_as_delegation(tmp_path, code):
    assert [d.confidence for d in _model(tmp_path, code)] == ["high"]


@pytest.mark.parametrize(
    "code",
    [
        "def a(self, rid):\n    rec = self.env['x.y'].sudo().browse(rid)\n    if not rec._can_be_edited_by_current_customer():\n        raise Forbidden()\n    rec.write({'a': 1})\n",
        "def a(self, rid):\n    rec = self.env['x.y'].sudo().browse(rid)\n    if rec.user_id != self.env.user:\n        raise AccessError('no')\n    rec.write({'a': 1})\n",
        "def a(self, rid):\n    rec = self.env['x.y'].sudo().browse(rid)\n    if rec.user_id != self.env.user:\n        raise werkzeug.exceptions.Forbidden()\n    rec.write({'a': 1})\n",
        "def a(self, rid):\n    rec = self.env['x.y'].sudo().browse(rid)\n    if not rec.is_allowed_for(self.env.user):\n        return False\n    rec.write({'a': 1})\n",
    ],
    ids=["can-method", "raise-access-error", "raise-qualified", "allowed-name"],
)
def test_a_rejection_path_or_a_check_style_name_counts_as_an_access_check(
    tmp_path, code
):
    assert _model(tmp_path, code) == []


@pytest.mark.parametrize(
    "code",
    [
        "def a(self, rid):\n    return self.env['x.y'].sudo().search([('id', '=', rid), ('user_id', '=', self.env.user.id)])\n",
        "def a(self, rid):\n    return self.env['x.y'].sudo().search([('id', '=', rid), ('user_id', '=', self.env.uid)])\n",
        "def a(self, rid):\n    uid = self.env.uid\n    return self.env['x.y'].sudo().browse(rid).filtered(lambda r: r.user_id.id == uid)\n",
    ],
    ids=["env.user", "env.uid", "uid-variable"],
)
def test_a_method_that_scopes_by_the_caller_is_only_medium(tmp_path, code):
    assert [d.confidence for d in _model(tmp_path, code)] == ["medium"]


@pytest.mark.parametrize(
    "code",
    [
        "def get(self, rid):\n    return self.env['x.y'].sudo().browse(rid).read(['name'])\n",
        "def get(self, domain):\n    return self.env['x.y'].sudo().search(domain)\n",
        "def get(self, rid):\n    records = self.env['x.y'].sudo()\n    return records.browse(rid).name\n",
    ],
    ids=["read", "search", "attribute"],
)
def test_a_parameter_reaching_an_elevated_read_is_medium(tmp_path, code):
    # many public RPCs read on purpose (codes, tokens, website data): review, do not score
    assert [d.confidence for d in _model(tmp_path, code)] == ["medium"]


@pytest.mark.parametrize(
    "code",
    [
        # search runs with the caller's rights, so what it returns is already filtered
        "def rm(self, ids):\n    orders = self.search([('id', 'in', ids)])\n    orders.sudo().unlink()\n",
        "def rm(self, domain):\n    self.search(domain).sudo().unlink()\n",
        # keys fixed by the code: not a mass assignment
        "def log(self, message):\n    self.env['ir.logging'].sudo().create({'name': 'x', 'message': message})\n",
        # the record is compared with the caller's own and refused otherwise
        "def edit(self, rid):\n    link = self.env['x.y'].browse(rid).sudo()\n    if link.owner_id not in self._owners():\n        return {'error': 'no'}\n    link.write({'a': 1})\n",
        "def edit(self, rid):\n    link = self.env['x.y'].browse(rid).sudo()\n    if link.owner_id != self.env.company.partner_id:\n        raise ValueError('no')\n    link.write({'a': 1})\n",
    ],
    ids=[
        "search-var",
        "search-inline",
        "constant-keys",
        "owner-compare-return",
        "owner-compare-raise",
    ],
)
def test_filtered_by_the_caller_or_compared_with_an_owner_is_not_reported(
    tmp_path, code
):
    assert _model(tmp_path, code) == []


def test_browse_does_not_filter_so_it_still_counts(tmp_path: Path):
    diags = _model(
        tmp_path,
        "def rm(self, ids):\n    orders = self.browse(ids)\n    orders.sudo().unlink()\n",
    )
    assert [d.confidence for d in diags] == ["high"]


def test_a_dict_with_a_parameter_as_the_whole_payload_still_counts(tmp_path: Path):
    diags = _model(
        tmp_path,
        "def make(self, vals):\n    return self.env['x.y'].sudo().create(dict(vals))\n",
    )
    assert [d.confidence for d in diags] == ["high"]
