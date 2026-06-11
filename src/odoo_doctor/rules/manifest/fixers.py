# src/odoo_doctor/rules/manifest/fixers.py
"""Auto-fixers for manifest rules."""

from __future__ import annotations

import ast

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import default_fixers

# Defaults for required manifest fields. Keys not present here are not
# auto-fillable (the fixer returns None and leaves the file untouched).
_FIELD_DEFAULTS: dict[str, object] = {
    "name": "",
    "version": "1.0.0",
    "depends": ["base"],
    "data": [],
    "installable": True,
    "license": "LGPL-3",
}


def _leading_comment_block(text: str) -> str:
    """Return the run of leading comment / blank lines (e.g. the coding header)
    so it can be re-attached after the dict is re-emitted."""
    header: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            header.append(line)
        else:
            break
    return "".join(header)


def fix_missing_required_field(diag: Diagnostic, text: str) -> str | None:
    """Fill ALL missing required manifest fields in one pass.

    The fixer does not depend on the diagnostic's title (which is a
    human-readable, i18n-able string). It re-derives which required fields are
    missing directly from the manifest text, so it is robust to title wording
    and naturally idempotent. compute_fixes may invoke it once per missing-field
    diagnostic on the same file; the first call fills everything and subsequent
    calls are no-ops.
    """
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(data, dict):
        return None

    missing = [
        key
        for key, default in _FIELD_DEFAULTS.items()
        if data.get(key) in (None, "")
    ]
    if not missing:
        return text  # nothing to do -> idempotent no-op

    for key in missing:
        data[key] = _FIELD_DEFAULTS[key]

    header = _leading_comment_block(text)
    return header + _format_manifest(data)


def _format_manifest(data: dict) -> str:
    """Emit a dict as a readable manifest literal, one key per line.

    Note: this normalizes the dict body (quotes/spacing). The leading comment
    block (coding header, license banner) is preserved by the caller via
    _leading_comment_block; inline comments inside the dict are not preserved.
    """
    lines = ["{"]
    for key, value in data.items():
        lines.append(f"    {key!r}: {value!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


default_fixers.register("manifest-missing-required-fields", fix_missing_required_field)


from odoo_doctor.rules.manifest.data_order_risk import _is_security_file


def fix_data_order_risk(diag: Diagnostic, text: str) -> str | None:
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return None

    files = data["data"]
    if not all(isinstance(f, str) for f in files):
        return None

    # Stable partition: security files first (original order), then everything
    # else (original order). Non-security/non-view files keep their slot in the
    # 'rest' bucket.
    security = [f for f in files if _is_security_file(f)]
    rest = [f for f in files if not _is_security_file(f)]
    reordered = security + rest

    if reordered == files:
        return text  # already correct -> idempotent no-op

    data["data"] = reordered
    return _format_manifest(data)


default_fixers.register("manifest-data-order-risk", fix_data_order_risk)
