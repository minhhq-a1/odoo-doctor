# src/odoo_doctor/core/text.py
"""The one sanitiser for repo-derived text printed to a terminal or a CI log."""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def safe_text(value: object) -> str:
    """``value`` as one line of plain text that cannot forge a log line.

    A newline in a file or module name would start a line of its own (``::error::`` at the
    start of a CI log line is a GitHub workflow command) and a raw ESC could drive the
    terminal, so control characters are shown as their escaped text. A word-wrapping
    renderer can also start a line at a repo-chosen ``::``, so every ``::`` gets an invisible
    zero-width space between the colons.
    """
    shown = _CONTROL.sub(
        lambda m: m.group().encode("unicode_escape").decode(), str(value)
    )
    return shown.replace("::", ":\u200b:")


def safe_lines(text: str) -> str:
    """Multi-line output of another tool (git's stderr): each line sanitised, lines kept."""
    return "\n".join(safe_text(line) for line in text.splitlines())
