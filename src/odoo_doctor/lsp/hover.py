# src/odoo_doctor/lsp/hover.py
"""Hover: explain the rule behind the finding under the cursor (pure, no server state).

The editor already shows a finding's message and help from the diagnostic itself, so the
hover adds what the diagnostic cannot: what the rule detects, why it matters, how to fix
it and a bad/good example, all from ``RULE_DOCS`` (the same source as ``rules explain``
and ``docs/rules.md``).
"""

from __future__ import annotations

from lsprotocol import types as lsp

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.lsp.convert import line_range
from odoo_doctor.rules.rule_docs import RULE_DOCS

_SEPARATOR = "\n\n---\n\n"


def _fence(code: str, lang: str) -> str:
    """A fenced block whose fence is longer than any backtick run inside *code*."""
    longest = run = 0
    for char in code:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{code}\n{fence}"


def _header(d: Diagnostic) -> str:
    return f"**{d.rule}** · {d.tier} · {d.severity} · confidence {d.confidence}"


def _explanation(d: Diagnostic) -> str:
    doc = RULE_DOCS.get(d.rule)
    parts = [_header(d)]
    if doc is None:
        # Ruff / Pylint-Odoo (or a plugin rule): no catalog entry, so show what we have.
        parts.append(f"_Reported by {d.source}._")
        if d.title:
            parts.append(d.title)
        if d.help:
            parts.append(f"**Fix.** {d.help}")
    else:
        parts.append(doc.detects)
        if doc.why:
            parts.append(f"**Why it matters.** {doc.why}")
        if doc.fix:
            parts.append(f"**Fix.** {doc.fix}")
        if doc.bad:
            parts.append("**Bad**\n\n" + _fence(doc.bad, doc.lang))
        if doc.good:
            parts.append("**Good**\n\n" + _fence(doc.good, doc.lang))
        if doc.notes:
            parts.append(doc.notes)
    if d.url:
        parts.append(f"[Documentation]({d.url})")
    return "\n\n".join(parts)


def hover_for(
    findings: list[Diagnostic], position: lsp.Position, line_text: str | None
) -> lsp.Hover | None:
    """The explanation of every finding on the hovered code, or None.

    A finding applies when the cursor is on its line and inside the code span (the same
    range its diagnostic underlines), so hovering the indentation or past the end of the
    line shows nothing.
    """
    on_line = [f for f in findings if max(f.line, 1) - 1 == position.line]
    if not on_line:
        return None
    span = line_range(on_line[0].line, line_text)
    if not span.start.character <= position.character <= span.end.character:
        return None
    return lsp.Hover(
        contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=_SEPARATOR.join(_explanation(f) for f in on_line),
        ),
        range=span,
    )
