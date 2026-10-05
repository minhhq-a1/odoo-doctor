# src/odoo_doctor/lsp/actions.py
"""Code actions for a finding: quick fix and the ways to switch the rule off."""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

from lsprotocol import types as lsp

import odoo_doctor.rules.manifest.fixers  # noqa: F401  (registers the fixers)
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.fixer import compute_fixes, default_fixers
from odoo_doctor.lsp.convert import diff_edits, position_at, split_lines
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.suppression import _SUPPRESS_FILE_RE

DISABLE_RULE_COMMAND = "odooDoctor.disableRule"

_RULES = r"([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)"
_PY_LINE = re.compile(rf"^(\s*)#\s*odoo-doctor:\s*disable={_RULES}\s*$")
_XML_LINE = re.compile(rf"^(\s*)<!--\s*odoo-doctor:\s*disable={_RULES}\s*-->\s*$")

_FSTRING_START = getattr(tokenize, "FSTRING_START", None)  # Python 3.12+
_FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def _suffix(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def _eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _comment(suffix: str, indent: str, kind: str, rules: str, eol: str) -> str:
    if suffix == ".xml":
        return f"{indent}<!-- odoo-doctor: {kind}={rules} -->{eol}"
    return f"{indent}# odoo-doctor: {kind}={rules}{eol}"


def _insert(lines: list[str], index: int, new_text: str, eol: str) -> lsp.TextEdit:
    """Insert *new_text* as whole line(s) before line *index* (may be EOF)."""
    pos = position_at(lines, index)
    if index == len(lines) and lines and not lines[-1].endswith(("\n", "\r")):
        new_text = eol + new_text  # the last line has no terminator yet
    return lsp.TextEdit(range=lsp.Range(start=pos, end=pos), new_text=new_text)


def _python_accepts_comment_before(text: str, lines: list[str], index: int) -> bool:
    """A whole-line comment before 0-based line *index* keeps the code valid and meaning.

    It would not inside a (triple-quoted or f-) string, where the comment becomes part of
    the string, nor after a backslash continuation, where it breaks the statement. If the
    file cannot be tokenized we cannot tell, so we say no.
    """
    if index > 0 and lines[index - 1].rstrip("\r\n").rstrip().endswith("\\"):
        return False
    line = index + 1
    fstring_starts: list[int] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.start[0] < line <= tok.end[0]:
                return False  # inside a multi-line token (a string)
            if _FSTRING_START is not None and tok.type == _FSTRING_START:
                fstring_starts.append(tok.start[0])
            elif _FSTRING_END is not None and tok.type == _FSTRING_END:
                started = fstring_starts.pop() if fstring_starts else tok.start[0]
                if started < line <= tok.end[0]:
                    return False
            if tok.start[0] > line:
                break
    except (tokenize.TokenError, SyntaxError):
        return False
    return True


def _xml_accepts_comment_before(lines: list[str], index: int) -> bool:
    """Only before a line that starts a tag, not inside one, and never before `<?xml`."""
    stripped = lines[index].lstrip()
    return stripped.startswith("<") and not stripped.startswith(("<?", "<![", "<!D"))


def disable_line_edit(
    rule: str, file_path: str, line: int, text: str
) -> lsp.TextEdit | None:
    """Comment on the line above the finding, which is how inline suppression works.

    Stacked comments do not work (a comment suppresses only the line right below it), so
    an existing ``disable=`` comment above is extended instead of duplicated. Returns None
    where the comment would not be safe or would not work.
    """
    suffix = _suffix(file_path)
    if suffix not in (".py", ".xml"):
        return None
    lines = split_lines(text)
    index = line - 1
    if index < 0 or index >= len(lines):
        return None
    eol = _eol(text)

    pattern = _XML_LINE if suffix == ".xml" else _PY_LINE
    previous = pattern.match(lines[index - 1].rstrip("\r\n")) if index > 0 else None
    if previous:
        rules = [r.strip() for r in previous.group(2).split(",")]
        if rule in rules:
            return None
        ending = lines[index - 1][len(lines[index - 1].rstrip("\r\n")) :] or eol
        merged = _comment(
            suffix, previous.group(1), "disable", ",".join(rules + [rule]), ending
        )
        return lsp.TextEdit(
            range=lsp.Range(
                start=position_at(lines, index - 1), end=position_at(lines, index)
            ),
            new_text=merged,
        )

    safe = (
        _xml_accepts_comment_before(lines, index)
        if suffix == ".xml"
        else _python_accepts_comment_before(text, lines, index)
    )
    if not safe:
        return None
    indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
    return _insert(lines, index, _comment(suffix, indent, "disable", rule, eol), eol)


def disable_file_edit(rule: str, file_path: str, text: str) -> lsp.TextEdit | None:
    """File-wide comment at the top, after a shebang or an XML declaration."""
    suffix = _suffix(file_path)
    if suffix not in (".py", ".xml"):
        return None
    for match in _SUPPRESS_FILE_RE.finditer(text):
        if rule in [r.strip() for r in match.group(1).split(",")]:
            return None
    lines = split_lines(text)
    eol = _eol(text)
    first = lines[0].lstrip() if lines else ""
    keep_first = (
        first.startswith("#!") if suffix == ".py" else first.startswith("<?xml")
    )
    return _insert(
        lines,
        1 if keep_first else 0,
        _comment(suffix, "", "disable-file", rule, eol),
        eol,
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


def line_in_sync(line: int, buffer_text: str, disk_text: str | None) -> bool:
    """Is the flagged line still where the last scan saw it?

    Findings come from the file on disk, the edit would be applied to the editor buffer.
    If lines were inserted or the flagged line itself was edited since the last save, an
    edit computed from the finding's line number would hit the wrong statement.
    """
    if disk_text is None:
        return False
    index = max(line, 1) - 1
    buffer_lines, disk_lines = split_lines(buffer_text), split_lines(disk_text)
    return (
        index < len(buffer_lines)
        and index < len(disk_lines)
        and buffer_lines[index] == disk_lines[index]
    )


def find_finding(
    findings: list[Diagnostic], diagnostic: lsp.Diagnostic
) -> Diagnostic | None:
    """The finding an LSP diagnostic was made from (same rule on the same line)."""
    line = diagnostic.range.start.line + 1
    for finding in findings:
        if finding.rule == diagnostic.code and max(finding.line, 1) == line:
            return finding
    return None


def _action(title: str, diagnostic: lsp.Diagnostic, **fields) -> lsp.CodeAction:
    return lsp.CodeAction(
        title=title,
        kind=lsp.CodeActionKind.QuickFix,
        diagnostics=[diagnostic],
        **fields,
    )


def code_actions_for(
    finding: Diagnostic,
    text: str,
    uri: str,
    diagnostic: lsp.Diagnostic,
    in_sync: bool = True,
) -> list[lsp.CodeAction]:
    """All actions offered on one finding: fix, disable on line / in file / in config.

    With ``in_sync=False`` (the buffer moved on since the last save) the actions that
    depend on the finding's line are left out.
    """
    rule = finding.rule
    actions: list[lsp.CodeAction] = []

    edits = fix_edits(finding, text) if in_sync else None
    if edits:
        actions.append(
            _action(
                f"Odoo Doctor: fix {rule}",
                diagnostic,
                is_preferred=True,
                edit=lsp.WorkspaceEdit(changes={uri: edits}),
            )
        )

    line_edit = (
        disable_line_edit(rule, finding.file_path, finding.line, text)
        if in_sync
        else None
    )
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
