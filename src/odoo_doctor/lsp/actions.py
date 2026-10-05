# src/odoo_doctor/lsp/actions.py
"""Code actions for a finding: quick fix and the ways to switch the rule off."""

from __future__ import annotations

import re
from pathlib import Path

from lsprotocol import types as lsp

import odoo_doctor.rules.manifest.fixers  # noqa: F401  (registers the fixers)
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import compute_fixes, default_fixers
from odoo_doctor.lsp.convert import diff_edits, position_at
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.suppression import _SUPPRESS_FILE_RE

DISABLE_RULE_COMMAND = "odooDoctor.disableRule"

_RULES = r"([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)"
_PY_LINE = re.compile(rf"^(\s*)#\s*odoo-doctor:\s*disable={_RULES}\s*$")
_XML_LINE = re.compile(rf"^(\s*)<!--\s*odoo-doctor:\s*disable={_RULES}\s*-->\s*$")


def _suffix(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def _comment(suffix: str, indent: str, kind: str, rules: str) -> str:
    if suffix == ".xml":
        return f"{indent}<!-- odoo-doctor: {kind}={rules} -->\n"
    return f"{indent}# odoo-doctor: {kind}={rules}\n"


def _insert(lines: list[str], index: int, new_text: str) -> lsp.TextEdit:
    """Insert *new_text* as whole line(s) before line *index* (may be EOF)."""
    pos = position_at(lines, index)
    if index == len(lines) and lines and not lines[-1].endswith(("\n", "\r")):
        new_text = "\n" + new_text  # the last line has no terminator yet
    return lsp.TextEdit(range=lsp.Range(start=pos, end=pos), new_text=new_text)


def disable_line_edit(
    rule: str, file_path: str, line: int, text: str
) -> lsp.TextEdit | None:
    """Comment on the line above the finding, which is how inline suppression works.

    Stacked comments do not work (a comment suppresses only the line right below it), so
    an existing ``disable=`` comment above is extended instead of duplicated.
    """
    suffix = _suffix(file_path)
    if suffix not in (".py", ".xml"):
        return None
    lines = text.splitlines(keepends=True)
    index = line - 1
    if index < 0 or index >= len(lines):
        return None

    pattern = _XML_LINE if suffix == ".xml" else _PY_LINE
    previous = pattern.match(lines[index - 1].rstrip("\r\n")) if index > 0 else None
    if previous:
        rules = [r.strip() for r in previous.group(2).split(",")]
        if rule in rules:
            return None
        merged = _comment(
            suffix, previous.group(1), "disable", ",".join(rules + [rule])
        )
        return lsp.TextEdit(
            range=lsp.Range(
                start=position_at(lines, index - 1), end=position_at(lines, index)
            ),
            new_text=merged,
        )

    indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
    return _insert(lines, index, _comment(suffix, indent, "disable", rule))


def disable_file_edit(rule: str, file_path: str, text: str) -> lsp.TextEdit | None:
    """File-wide comment at the top, after a shebang or an XML declaration."""
    suffix = _suffix(file_path)
    if suffix not in (".py", ".xml"):
        return None
    for match in _SUPPRESS_FILE_RE.finditer(text):
        if rule in [r.strip() for r in match.group(1).split(",")]:
            return None
    lines = text.splitlines(keepends=True)
    first = lines[0].lstrip() if lines else ""
    keep_first = (
        first.startswith("#!") if suffix == ".py" else first.startswith("<?xml")
    )
    return _insert(
        lines, 1 if keep_first else 0, _comment(suffix, "", "disable-file", rule)
    )


def fix_edits(finding: Diagnostic, text: str) -> list[lsp.TextEdit] | None:
    """Edits from the deterministic fixer of the finding's rule, if it has one."""
    entry = default_registry.get(finding.rule)
    fixable = {finding.rule} if entry and entry[0].fixable else set()
    result, _ = compute_fixes(
        [finding], fixable, default_fixers, read_text=lambda _path: text
    )
    new_text = result.changed_files.get(finding.file_path)
    if new_text is None or new_text == text:
        return None
    return diff_edits(text, new_text)


def _action(title: str, diagnostic: lsp.Diagnostic, **fields) -> lsp.CodeAction:
    return lsp.CodeAction(
        title=title,
        kind=lsp.CodeActionKind.QuickFix,
        diagnostics=[diagnostic],
        **fields,
    )


def code_actions_for(
    finding: Diagnostic, text: str, uri: str, diagnostic: lsp.Diagnostic
) -> list[lsp.CodeAction]:
    """All actions offered on one finding: fix, disable on line / in file / in config."""
    rule = finding.rule
    actions: list[lsp.CodeAction] = []

    edits = fix_edits(finding, text)
    if edits:
        actions.append(
            _action(
                f"Odoo Doctor: fix {rule}",
                diagnostic,
                is_preferred=True,
                edit=lsp.WorkspaceEdit(changes={uri: edits}),
            )
        )

    line_edit = disable_line_edit(rule, finding.file_path, finding.line, text)
    if line_edit:
        actions.append(
            _action(
                f"Odoo Doctor: disable {rule} on this line",
                diagnostic,
                edit=lsp.WorkspaceEdit(changes={uri: [line_edit]}),
            )
        )

    file_edit = disable_file_edit(rule, finding.file_path, text)
    if file_edit:
        actions.append(
            _action(
                f"Odoo Doctor: disable {rule} in this file",
                diagnostic,
                edit=lsp.WorkspaceEdit(changes={uri: [file_edit]}),
            )
        )

    title = f"Odoo Doctor: disable {rule} in odoo-doctor.toml"
    actions.append(
        _action(
            title,
            diagnostic,
            command=lsp.Command(
                title=title, command=DISABLE_RULE_COMMAND, arguments=[rule, uri]
            ),
        )
    )
    return actions
