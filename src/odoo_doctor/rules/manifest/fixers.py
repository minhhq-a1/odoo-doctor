# src/odoo_doctor/rules/manifest/fixers.py
"""Auto-fixers for manifest rules."""

from __future__ import annotations

import ast
import re
import tokenize
from io import StringIO
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import default_fixers
from odoo_doctor.rules.manifest.data_order_risk import safe_placement
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


default_fixers.register("manifest-missing-required-fields", fix_missing_required_field)


def _data_list_blocks(text: str) -> tuple[list[str], list[str], int] | None:
    """(file names, one text block per element, index of the first element's line).

    None unless the `data` list has exactly one element per line, with nothing between
    the elements but each element's own trailing comma and `#` comment.
    """
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Dict):
        return None
    value = next(
        (
            v
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and k.value == "data"
        ),
        None,
    )
    if not isinstance(value, ast.List) or not value.elts:
        return None
    elts = value.elts
    if not all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elts):
        return None
    lines = text.splitlines(keepends=True)
    blocks: list[str] = []
    for i, e in enumerate(elts):
        if e.end_lineno != e.lineno or (i and e.lineno != elts[i - 1].lineno + 1):
            return None
        raw = lines[e.lineno - 1].encode("utf-8")
        before = raw[: e.col_offset].decode("utf-8")
        after = raw[e.end_col_offset :].decode("utf-8")  # type: ignore[index]
        if before.strip() or not re.fullmatch(r"\s*,\s*(#.*)?", after, re.DOTALL):
            return None
        blocks.append(lines[e.lineno - 1])
    return [e.value for e in elts], blocks, elts[0].lineno - 1  # type: ignore[attr-defined]


def fix_data_order_risk(diag: Diagnostic, text: str) -> str | None:
    """Move each `high` security file in front of the first file that needs its group.

    A local edit of the `data` lines (comments and every other byte stay); `None` when
    the list is not one element per line or the new position cannot be shown safe.
    """
    module_dir = Path(diag.file_path).parent
    parsed = _data_list_blocks(text)
    if parsed is None:
        return None
    files, blocks, first_line = parsed
    if len(set(files)) != len(files):
        return None
    placement = safe_placement(module_dir, module_dir.name, files)
    if placement is None:
        return None
    if not placement:
        return text  # nothing is high -> idempotent no-op
    moved = {files.index(f) for f in placement}
    targets = {files.index(f): t for f, t in placement.items()}
    if any(t in moved for t in targets.values()):
        return None  # chained moves: not shown to be safe
    order: list[int] = []
    for i in range(len(files)):
        if i in moved:
            continue
        order += [m for m in sorted(moved) if targets[m] == i]
        order.append(i)
    if order == list(range(len(files))):
        return text
    lines = text.splitlines(keepends=True)
    lines[first_line : first_line + len(blocks)] = [blocks[i] for i in order]
    return "".join(lines)


default_fixers.register("manifest-data-order-risk", fix_data_order_risk)
