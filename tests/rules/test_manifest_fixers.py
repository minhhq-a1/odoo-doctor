"""Fixer for manifest-missing-required-fields inserts default keys."""

from __future__ import annotations

import ast

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.manifest.fixers import fix_missing_required_field

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


def test_fills_all_missing_required_fields_at_once():
    src = "{'name': 'M'}"
    out = fix_missing_required_field(_diag(), src)
    parsed = ast.literal_eval(out)
    for key in ("version", "depends", "data", "installable", "license"):
        assert key in parsed


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
