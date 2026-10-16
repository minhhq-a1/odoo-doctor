# src/odoo_doctor/rules/manifest/fixers.py
"""Auto-fixers for manifest rules."""

from __future__ import annotations

import ast
import tokenize
from io import StringIO

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import default_fixers
from odoo_doctor.rules.manifest.data_order_risk import _is_security_file
from odoo_doctor.rules.manifest.missing_required_fields import (
    missing_fields_by_confidence,
)

# Defaults for required manifest fields. Keys with an empty default (`name`) are
# never filled: the rule would still count "" as missing, so the fix would repeat.
_FIELD_DEFAULTS: dict[str, object] = {
    "name": "",
    "version": "1.0.0",
    "depends": ["base"],
    "data": [],
    "license": "LGPL-3",
}


def _last_token_is_comma(source: str) -> bool:
    """Is the last significant token of *source* a comma? (comments/newlines ignored)"""
    last = None
    try:
        for tok in tokenize.generate_tokens(StringIO(source).readline):
            if tok.type not in (
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                last = tok.string
    except (tokenize.TokenError, IndentationError):
        pass  # expected: the text is cut before the closing brace, so the bracket is open
    return last == ","


def _insert_entries(text: str, entries: list[tuple[str, object]]) -> str | None:
    """Add `'key': value` entries before the closing brace; no existing byte is changed."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Dict) or node.end_lineno is None:
        return None
    lines = text.splitlines(keepends=True)
    row = node.end_lineno - 1
    brace = len(lines[row].encode("utf-8")[: node.end_col_offset - 1].decode("utf-8"))
    before = lines[row][:brace]
    has_items = bool(node.keys)
    comma = has_items and _last_token_is_comma(
        text[: sum(len(x) for x in lines[:row]) + brace]
    )
    if before.strip() == "" and node.lineno != node.end_lineno:
        # the closing brace is alone on its line: one new line per entry
        if has_items and not comma:
            return None
        if has_items:
            last_key_line = lines[node.keys[-1].lineno - 1]
            indent = last_key_line[: len(last_key_line) - len(last_key_line.lstrip())]
        else:
            indent = "    "
        lines.insert(row, "".join(f"{indent}{k!r}: {v!r},\n" for k, v in entries))
        return "".join(lines)
    # the brace shares its line with the last entry (or the dict is `{}`): append inline
    # right after the last token, so the whitespace that was already there stays
    cut = len(before.rstrip())
    sep = "" if not has_items else (" " if comma else ", ")
    inline = sep + ", ".join(f"{k!r}: {v!r}" for k, v in entries)
    lines[row] = before[:cut] + inline + before[cut:] + lines[row][brace:]
    return "".join(lines)


def fix_missing_required_field(diag: Diagnostic, text: str) -> str | None:
    """Add the absent high-confidence required fields that have a default.

    A local edit: `version` and `data` are medium and are left alone, and every
    other byte of the file is kept. A missing `name` or an existing-but-empty value
    is reported as not fixable. The fixer re-derives what is missing from the text
    (not from the diagnostic), so it is idempotent when called once per diagnostic.
    """
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(data, dict):
        return None

    missing, _medium = missing_fields_by_confidence(data)
    if not missing:
        return text  # nothing to do -> idempotent no-op
    addable = [
        k for k in missing if k not in data and _FIELD_DEFAULTS[k] not in ("", None)
    ]
    if not addable:
        return None
    return _insert_entries(text, [(k, _FIELD_DEFAULTS[k]) for k in addable])


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
