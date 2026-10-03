# src/odoo_doctor/core/config_edit.py
"""Minimal, comment-preserving edits to odoo-doctor.toml.

No TOML writer dependency: only the ``[ignore] rules = [...]`` array is touched
and every other line of the file is left byte-for-byte as it was.
"""

from __future__ import annotations

import re
from pathlib import Path

_SECTION_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")
_RULES_RE = re.compile(r"^(\s*)rules\s*=\s*\[(.*?)\]", re.DOTALL | re.MULTILINE)
_ITEM_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')


def _format_rules(rules: list[str]) -> str:
    return "rules = [" + ", ".join(f'"{r}"' for r in rules) + "]"


def set_rule_ignored(config_path: Path, rule: str, ignored: bool) -> bool:
    """Add (ignored=True) or remove (ignored=False) *rule* in ``[ignore] rules``.

    Creates the file/section when needed. Returns True if the file changed.
    """
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = text.splitlines(keepends=True)

    start = end = None
    for i, line in enumerate(lines):
        m = _SECTION_RE.match(line.rstrip("\r\n"))
        if m is None:
            continue
        if start is None and m.group(1).strip() == "ignore":
            start = i
        elif start is not None:
            end = i
            break
    if start is not None and end is None:
        end = len(lines)

    if start is None:
        if not ignored:
            return False
        prefix = "" if not text or text.endswith("\n") else "\n"
        sep = "\n" if text else ""
        new_text = f"{text}{prefix}{sep}[ignore]\n{_format_rules([rule])}\n"
        config_path.write_text(new_text, encoding="utf-8")
        return True

    body = "".join(lines[start + 1 : end])
    match = _RULES_RE.search(body)
    if match is None:
        if not ignored:
            return False
        new_body = f"{_format_rules([rule])}\n" + body
    else:
        current = [a or b for a, b in _ITEM_RE.findall(match.group(2))]
        if ignored == (rule in current):
            return False
        updated = current + [rule] if ignored else [r for r in current if r != rule]
        replacement = match.group(1) + _format_rules(updated)
        new_body = body[: match.start()] + replacement + body[match.end() :]

    new_text = "".join(lines[: start + 1]) + new_body + "".join(lines[end:])
    config_path.write_text(new_text, encoding="utf-8")
    return True
