# src/odoo_doctor/rules/suppression.py
"""Scan for inline suppression comments: # odoo-doctor: disable=<rule>."""

from __future__ import annotations

import re
import tokenize
from pathlib import Path

from lxml import etree

_SUPPRESS_RE = re.compile(r"odoo-doctor:\s*disable=([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)")
_SUPPRESS_FILE_RE = re.compile(r"odoo-doctor:\s*disable-file=([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)")

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

        # File-wide: line 0 sentinel
        file_match = _SUPPRESS_FILE_RE.search(tok.string)
        if file_match:
            for rule_name in (r.strip() for r in file_match.group(1).split(",")):
                suppressions.add((str(file_path), 0, rule_name))
            continue

        # Line-level: suppress the next line
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

    # Collect all comments: those inside root via iter, plus preceding siblings of root
    root = tree.getroot()
    comments = list(tree.iter(etree.Comment))
    # Also grab document-level comments that appear before the root element
    if root is not None:
        for sibling in root.itersiblings(etree.Comment, preceding=True):
            if sibling not in comments:
                comments.append(sibling)

    for comment in comments:
        text = comment.text or ""

        # File-wide
        file_match = _SUPPRESS_FILE_RE.search(text)
        if file_match:
            for rule_name in (r.strip() for r in file_match.group(1).split(",")):
                suppressions.add((str(file_path), 0, rule_name))
            continue

        # Line-level
        match = _SUPPRESS_RE.search(text)
        if not match:
            continue

        rules = [r.strip() for r in match.group(1).split(",")]
        suppress_line = (comment.sourceline or 0) + 1
        for rule_name in rules:
            suppressions.add((str(file_path), suppress_line, rule_name))

    return suppressions
