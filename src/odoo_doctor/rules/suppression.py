# src/odoo_doctor/rules/suppression.py
"""Scan for inline suppression comments: # odoo-doctor: disable=<rule>."""

from __future__ import annotations

import re
import tokenize
from pathlib import Path

from lxml import etree

_SUPPRESS_RE = re.compile(r"odoo-doctor:\s*disable=([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)")

Suppressions = set[tuple[str, int, str]]  # (file_path, line, rule)


def scan_python_suppressions(file_path: Path) -> Suppressions:
    """Scan a Python file for inline suppression comments."""
    suppressions: Suppressions = set()

    try:
        with open(file_path, "rb") as f:
            tokens = list(tokenize.tokenize(f.readline))
    except (tokenize.TokenError, SyntaxError, OSError):
        return suppressions

    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _SUPPRESS_RE.search(tok.string)
        if not match:
            continue

        rules = [r.strip() for r in match.group(1).split(",")]
        suppress_line = tok.start[0] + 1
        for rule_name in rules:
            suppressions.add((str(file_path), suppress_line, rule_name))

    return suppressions


def scan_xml_suppressions(file_path: Path) -> Suppressions:
    """Scan an XML file for inline suppression comments."""
    suppressions: Suppressions = set()

    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return suppressions

    for comment in tree.iter(etree.Comment):
        match = _SUPPRESS_RE.search(comment.text or "")
        if not match:
            continue

        rules = [r.strip() for r in match.group(1).split(",")]
        suppress_line = (comment.sourceline or 0) + 1
        for rule_name in rules:
            suppressions.add((str(file_path), suppress_line, rule_name))

    return suppressions
