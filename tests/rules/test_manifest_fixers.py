"""Fixer for manifest-missing-required-fields inserts default keys."""

from __future__ import annotations

import ast

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.manifest.fixers import (
    fix_data_order_risk,
    fix_missing_required_field,
)

_DEFAULTS = {
    "name": "",
    "version": "1.0.0",
    "depends": ["base"],
    "data": [],
    "installable": True,
    "license": "LGPL-3",
}


# The fixer ignores the diagnostic's title and fills all missing required
# fields from the manifest text, so a single generic diagnostic is enough.
def _diag() -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path="m/__manifest__.py",
        line=1,
        column=0,
        rule="manifest-missing-required-fields",
        category="Module Hygiene",
        severity="warning",
        tier="P2",
        source="native",
        confidence="high",
        title="Manifest missing required field",
        message="...",
        help="...",
        odoo_version="17.0",
    )


def test_inserts_missing_depends_as_list():
    src = "{'name': 'M', 'version': '1.0', 'data': [], 'installable': True, 'license': 'LGPL-3'}"
    out = fix_missing_required_field(_diag(), src)
    parsed = ast.literal_eval(out)
    assert parsed["depends"] == ["base"]


def test_inserts_missing_license_as_string():
    src = "{'name': 'M', 'version': '1.0', 'depends': [], 'data': [], 'installable': True}"
    out = fix_missing_required_field(_diag(), src)
    parsed = ast.literal_eval(out)
    assert parsed["license"] == "LGPL-3"


def test_fills_all_missing_high_confidence_fields_at_once():
    src = "{'name': 'M'}"
    out = fix_missing_required_field(_diag(), src)
    parsed = ast.literal_eval(out)
    for key in ("depends", "license"):
        assert key in parsed
    assert "version" not in parsed and "data" not in parsed  # medium: left alone
    assert "installable" not in parsed  # Odoo defaults it to True


def test_preserves_leading_coding_header():
    src = "# -*- coding: utf-8 -*-\n{'name': 'M', 'version': '1.0'}"
    out = fix_missing_required_field(_diag(), src)
    assert out.startswith("# -*- coding: utf-8 -*-")
    assert ast.literal_eval(out.split("\n", 1)[1])["license"] == "LGPL-3"


def test_idempotent_when_all_present():
    src = "{'name': 'M', 'version': '1.0', 'depends': ['base'], 'data': [], 'installable': True, 'license': 'LGPL-3'}"
    out = fix_missing_required_field(_diag(), src)
    assert out == src  # nothing missing -> unchanged


def test_returns_none_on_unparseable_manifest():
    assert fix_missing_required_field(_diag(), "{'name': ") is None


def _order_diag() -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path="m/__manifest__.py",
        line=1,
        column=0,
        rule="manifest-data-order-risk",
        category="Module Hygiene",
        severity="error",
        tier="P2",
        source="native",
        confidence="high",
        title="Security file loaded after views/actions",
        message="...",
        help="...",
        odoo_version="17.0",
    )


def test_reorders_security_before_views():
    src = "{'name': 'M', 'data': ['views/my_view.xml', 'security/ir.model.access.csv']}"
    out = fix_data_order_risk(_order_diag(), src)
    data = ast.literal_eval(out)["data"]
    assert data.index("security/ir.model.access.csv") < data.index("views/my_view.xml")


def test_data_order_idempotent_when_already_correct():
    src = "{'name': 'M', 'data': ['security/ir.model.access.csv', 'views/my_view.xml']}"
    out = fix_data_order_risk(_order_diag(), src)
    data = ast.literal_eval(out)["data"]
    assert data == ["security/ir.model.access.csv", "views/my_view.xml"]


COMMENTED = (
    "# -*- coding: utf-8 -*-\n"
    "# keep this header\n"
    "{\n"
    "    'name': 'M',  # trailing note\n"
    "    'depends': ['base'],\n"
    '    "category": "Tools",   # double quotes on purpose\n'
    "}\n"
)


def test_missing_field_fixer_adds_only_high_fields_and_keeps_every_other_byte():
    # `license` is high (fix it); `version` and `data` are medium (leave them)
    out = fix_missing_required_field(_diag(), COMMENTED)
    assert out is not None
    head, tail = COMMENTED[:-2], "}\n"  # everything before the closing brace line
    assert out.startswith(head) and out.endswith(tail)
    assert out[len(head) : -len(tail)] == "    'license': 'LGPL-3',\n"
    assert fix_missing_required_field(_diag(), out) == out  # idempotent


def test_missing_field_fixer_is_a_no_op_when_only_medium_fields_are_missing():
    src = "{'name': 'M', 'depends': ['base'], 'license': 'LGPL-3'}"
    assert fix_missing_required_field(_diag(), src) == src


def test_missing_field_fixer_on_a_one_line_dict_inserts_before_the_brace():
    src = "{'name': 'M', 'depends': ['base']}"
    assert (
        fix_missing_required_field(_diag(), src)
        == "{'name': 'M', 'depends': ['base'], 'license': 'LGPL-3'}"
    )


def test_missing_field_fixer_refuses_when_it_cannot_edit_locally():
    # no trailing comma before the closing brace line: adding a line would need a
    # comma on a line that may carry a comment, so the fixer declines
    src = "{\n    'name': 'M',\n    'depends': ['base']\n}\n"
    assert fix_missing_required_field(_diag(), src) is None


def test_missing_field_fixer_handles_empty_dicts_and_never_inserts_twice():
    for src in ("{}", "{ }", "{\n}\n"):
        out = fix_missing_required_field(_diag(), src)
        assert out is not None, src
        # `name` has no usable default, so it is not filled (it would stay "missing")
        assert ast.literal_eval(out) == {"depends": ["base"], "license": "LGPL-3"}
        again = fix_missing_required_field(_diag(), out)
        assert again in (None, out)  # a second run adds nothing
        assert out.count("'depends'") == 1 and out.count("'license'") == 1


def test_missing_field_fixer_does_not_touch_empty_values_or_a_lone_missing_name():
    # `license` exists but is empty, `name` is absent: nothing can be added safely
    assert (
        fix_missing_required_field(
            _diag(), "{'name': 'M', 'depends': ['base'], 'license': ''}"
        )
        is None
    )
    assert (
        fix_missing_required_field(
            _diag(), "{'depends': ['base'], 'license': 'LGPL-3'}"
        )
        is None
    )


def test_missing_field_fixer_keeps_existing_whitespace_before_the_brace():
    out = fix_missing_required_field(_diag(), "{'name': 'M', 'depends': ['base'] }")
    assert out == "{'name': 'M', 'depends': ['base'], 'license': 'LGPL-3' }"
