# src/odoo_doctor/lsp/convert.py
"""Pure conversions between odoo-doctor findings and LSP types (no server state)."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from lsprotocol import types as lsp

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import default_registry

SOURCE = "odoo-doctor"

_LINES = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+")


def split_lines(text: str) -> list[str]:
    """Lines with their terminators, split like Python and LSP do (\\n, \\r\\n, \\r).

    Not ``str.splitlines``: that also breaks on form feed, \\x1c-\\x1e, \\x85 and the
    Unicode separators, which would shift every line number after one of them.
    """
    return _LINES.findall(text)


_SEVERITY = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
    "info": lsp.DiagnosticSeverity.Information,
}


def to_lsp_diagnostic(
    d: Diagnostic, line_text: str | None, fixable: bool = False
) -> lsp.Diagnostic:
    """Map a finding to an LSP diagnostic.

    The range spans the code on the finding's line (first non-blank character to the end
    of the line). ``Diagnostic.column`` is not used: its base differs between native
    rules and the Ruff / Pylint adapters. Without the line text the range is empty.
    """
    line = max(d.line - 1, 0)
    start = end = 0
    if line_text is not None:
        text = line_text.rstrip("\r\n")
        if text.strip():
            start = len(text) - len(text.lstrip())
            end = len(text.rstrip())
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=line, character=start),
            end=lsp.Position(line=line, character=max(end, start)),
        ),
        message=f"{d.message}\n{d.help}" if d.help else d.message,
        severity=_SEVERITY.get(d.severity, lsp.DiagnosticSeverity.Information),
        code=d.rule,
        code_description=(lsp.CodeDescription(href=d.url) if d.url else None),
        source=SOURCE,
        data={"rule": d.rule, "fixable": fixable},
    )


def position_at(lines: list[str], index: int) -> lsp.Position:
    """Position of the start of line *index*; at EOF, the end of an unterminated text."""
    if index < len(lines):
        return lsp.Position(line=index, character=0)
    if not lines or lines[-1].endswith(("\n", "\r")):
        return lsp.Position(line=len(lines), character=0)
    return lsp.Position(line=len(lines) - 1, character=len(lines[-1]))


def diff_edits(old: str, new: str) -> list[lsp.TextEdit]:
    """Minimal line-based edits turning *old* into *new* (empty when equal)."""
    old_lines = split_lines(old)
    new_lines = split_lines(new)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    edits: list[lsp.TextEdit] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits.append(
            lsp.TextEdit(
                range=lsp.Range(
                    start=position_at(old_lines, i1), end=position_at(old_lines, i2)
                ),
                new_text="".join(new_lines[j1:j2]),
            )
        )
    return edits


def _is_fixable(rule: str) -> bool:
    entry = default_registry.get(rule)
    return bool(entry and entry[0].fixable)


def file_diagnostics(
    file_path: str, findings: list[Diagnostic]
) -> list[lsp.Diagnostic]:
    """LSP diagnostics for all findings in one file (reads the file for the ranges)."""
    try:
        text = Path(file_path).read_text(encoding="utf-8")
        lines = [line.rstrip("\r\n") for line in split_lines(text)]
    except (OSError, UnicodeDecodeError):
        lines = None
    result = []
    for d in findings:
        index = d.line - 1
        text = lines[index] if lines is not None and 0 <= index < len(lines) else None
        result.append(to_lsp_diagnostic(d, text, fixable=_is_fixable(d.rule)))
    return result
