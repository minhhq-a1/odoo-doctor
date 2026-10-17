# src/odoo_doctor/rules/security/sudo_without_comment.py
"""Rule: sudo-without-comment [Security, P1]."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule


def _comment(line: str) -> str | None:
    """The comment text of a line, or None. Strings are stripped crudely, which is good
    enough for a heuristic."""
    in_str = None
    for i, ch in enumerate(line):
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
        elif ch == "#":
            return line[i + 1 :]
    return None


def _line_has_comment(line: str) -> bool:
    return _comment(line) is not None


# A comment that names sudo explains it even when a statement or two come between.
_NOTE_WINDOW = 5
_BOUNDARY = ("def ", "async def ", "class ", "@")
# shortcut: any comment or docstring containing the word counts, whatever it says
# (`# TODO remove sudo`, `# never use sudo here`), upgrade to a `sudo:` marker or a
# reason check if such notes show up as false negatives.
_SUDO_WORD = re.compile(r"\bsudo\b", re.IGNORECASE)
# Calls that keep the environment of their receiver (and so its superuser mode).
_KEEPS_ENV = {"with_context", "browse", "exists"}


def _calls_with_statement(tree: ast.AST):
    """Yield every ``ast.Call`` with the innermost statement that contains it."""
    stack: list[tuple[ast.AST, ast.stmt | None]] = [(tree, None)]
    while stack:
        node, stmt = stack.pop()
        if isinstance(node, ast.stmt):
            stmt = node
        if isinstance(node, ast.Call):
            yield node, stmt
        stack.extend((child, stmt) for child in ast.iter_child_nodes(node))


def _drops_privileges(call: ast.Call) -> bool:
    """``.sudo(False)`` returns the non-superuser environment: nothing to justify."""
    values = [*call.args[:1], *(k.value for k in call.keywords)]
    return any(isinstance(v, ast.Constant) and v.value is False for v in values)


def _statement_span(stmt: ast.stmt) -> tuple[int, int]:
    """Lines of the statement itself; for a compound one, its header only (a comment in
    the body says nothing about a ``sudo()`` in the ``if`` / ``for`` / ``with`` line)."""
    nested = (ast.stmt, ast.ExceptHandler, ast.match_case)
    children = list(ast.iter_child_nodes(stmt))
    if not any(isinstance(c, nested) for c in children):
        return stmt.lineno, stmt.end_lineno or stmt.lineno
    end = stmt.lineno
    for child in children:
        if isinstance(child, nested):
            continue
        for n in ast.walk(child):
            end = max(end, getattr(n, "end_lineno", None) or 0)
    return stmt.lineno, end


def _names_sudo(line: str) -> bool:
    return bool(_SUDO_WORD.search(_comment(line) or ""))


def _is_justified(lines: list[str], span: tuple[int, int], sudo_line: int) -> bool:
    """A comment on any line of the statement, or on the line right above its start or
    above the ``.sudo()`` line (a chain can put ``.sudo()`` several lines down), or a
    comment naming sudo within a few lines above the statement."""
    first, last = span
    for lineno in range(first - 1, max(0, first - 1 - _NOTE_WINDOW), -1):
        if lineno > len(lines):
            continue
        if lines[lineno - 1].lstrip().startswith(_BOUNDARY):
            break  # the note of the function above says nothing about this one
        if _names_sudo(lines[lineno - 1]):
            return True
    for lineno in range(first, last + 1):
        if 0 < lineno <= len(lines) and _line_has_comment(lines[lineno - 1]):
            return True
    for lineno in {first, sudo_line}:
        if lineno >= 2 and lines[lineno - 2].strip().startswith("#"):
            return True
    return False


def _self_rebinds_to_sudo(stmt: ast.stmt) -> bool:
    """``self = self.sudo()``."""
    return (
        isinstance(stmt, ast.Assign)
        and [t.id for t in stmt.targets if isinstance(t, ast.Name)] == ["self"]
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "sudo"
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == "self"
        and not stmt.value.args  # `.sudo(False)` / `.sudo(user)` is not a bare elevation
        and not stmt.value.keywords
    )


def _later_rebinding(fn: ast.AST, after: int) -> int | None:
    """First line past ``after`` where ``self`` is bound again, at any depth."""
    lines = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(
            node,
            (ast.AugAssign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor),
        ):
            targets = [node.target]
        else:
            continue
        if node.lineno > after and any(
            isinstance(n, ast.Name) and n.id == "self" and isinstance(n.ctx, ast.Store)
            for t in targets
            for n in ast.walk(t)
        ):
            lines.append(node.lineno)
    return min(lines) if lines else None


def _sudo_ranges(tree: ast.AST) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Line ranges where a ``.sudo()`` needs no comment: functions whose docstring names
    sudo (any call), and the rest of a function after a top-level ``self = self.sudo()``
    (calls built from ``self``, which are already superuser there)."""
    documented: list[tuple[int, int]] = []
    elevated: list[tuple[int, int]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = fn.end_lineno or fn.lineno
        if _SUDO_WORD.search(ast.get_docstring(fn) or ""):
            documented.append((fn.lineno, end))
        for stmt in fn.body:
            if _self_rebinds_to_sudo(stmt):
                start = stmt.end_lineno or stmt.lineno
                # `self = self.with_user(5)` later ends the elevation
                stop = _later_rebinding(fn, start)
                elevated.append((start, stop - 1 if stop else end))
                break
    return documented, elevated


def _rooted_in_self(call: ast.Call) -> bool:
    """``self.env[...].sudo()`` / ``self.sudo()``: the receiver is built from ``self``
    without changing its user."""
    node = call.func.value if isinstance(call.func, ast.Attribute) else None
    while node is not None:
        if isinstance(node, ast.Name):
            return node.id == "self"
        if (isinstance(node, ast.Attribute) and node.attr == "env") or isinstance(
            node, ast.Subscript
        ):
            node = node.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _KEEPS_ENV
        ):
            node = node.func.value
        else:
            return False
    return False


@rule(
    name="sudo-without-comment",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="low",
    needs_context=False,
    min_version="14.0",
)
def check_sudo_without_comment(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    if is_test_file(file_path, module_name) or "migrations" in Path(file_path).parts:
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    lines = (read_source(file_path) or "").splitlines()

    documented, elevated = _sudo_ranges(tree)
    diags: list[Diagnostic] = []
    for node, stmt in _calls_with_statement(tree):
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "sudo"):
            continue
        if _drops_privileges(node):
            continue
        lineno = node.lineno
        # shortcut: ranges are by line, so a nested function inherits its parent's.
        if any(a <= lineno <= b for a, b in documented) or (
            _rooted_in_self(node) and any(a < lineno <= b for a, b in elevated)
        ):
            continue
        span = _statement_span(stmt) if stmt is not None else (lineno, lineno)
        if _is_justified(lines, span, node.func.end_lineno or lineno):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=lineno,
                column=node.col_offset,
                rule="sudo-without-comment",
                category="Security",
                severity="warning",
                tier="P1",
                source="native",
                confidence="low",
                title="'.sudo()' without a justifying comment",
                message=(
                    f".sudo() at line {lineno} bypasses access rights but has "
                    "no comment explaining why it is safe."
                ),
                help=(
                    "Add a short comment on the same line or directly above "
                    "explaining why elevated privileges are required."
                ),
                odoo_version=odoo_version,
            )
        )
    return sorted(diags, key=lambda d: (d.line, d.column))
