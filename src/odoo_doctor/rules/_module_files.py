# src/odoo_doctor/rules/_module_files.py
"""Shared file and XML-record helpers for rules that read a whole module."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Directories below an addon whose Python is not module code: tests, one-off upgrade
# scripts and bundled front-end sources.
_SKIPPED_DIRS = {"tests", "migrations", "upgrades", "static", "i18n", "__pycache__"}


def data_files(ctx: ModuleContext) -> list[Path]:
    """Existing XML files the manifest loads (data and demo), in manifest order."""
    names = list(ctx.manifest.data)
    demo = ctx.manifest.raw.get("demo", [])
    if isinstance(demo, list):
        names += [n for n in demo if isinstance(n, str)]
    seen, files = set(), []
    for name in names:
        path = ctx.path / name
        if path.suffix == ".xml" and path.exists() and path not in seen:
            seen.add(path)
            files.append(path)
    return files


def python_files(ctx: ModuleContext) -> list[Path]:
    """The module's Python source, without tests, migration scripts and static assets."""
    files = []
    for path in sorted(ctx.path.rglob("*.py")):
        below = path.relative_to(ctx.path).parts[:-1]
        if _SKIPPED_DIRS & set(below):
            continue
        files.append(path)
    return files


def parse_xml(path: Path) -> etree._ElementTree | None:
    try:
        return etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError):
        return None


def records(tree: etree._ElementTree, model: str) -> Iterator[etree._Element]:
    for record in tree.iter("record"):
        if record.get("model") == model:
            yield record


def field_of(record: etree._Element, name: str) -> etree._Element | None:
    return next((f for f in record.findall("field") if f.get("name") == name), None)


def field_text(record: etree._Element, name: str) -> str:
    field = field_of(record, name)
    return (field.text or "").strip() if field is not None else ""


def is_explicit_qweb(record: etree._Element) -> bool:
    """A view record that declares ``type`` qweb: a template, not a view architecture."""
    return field_text(record, "type") == "qweb"


def view_arches(
    tree: etree._ElementTree,
) -> Iterator[tuple[etree._Element, etree._Element]]:
    """``(record, arch field)`` of every non-QWeb ``ir.ui.view`` record."""
    for record in records(tree, "ir.ui.view"):
        arch = field_of(record, "arch")
        if arch is not None and not is_explicit_qweb(record):
            yield record, arch


def elements(node: etree._Element) -> Iterator[etree._Element]:
    """Element descendants, without comments and processing instructions."""
    for el in node.iter():
        if isinstance(el.tag, str):
            yield el


def line_of(*nodes: etree._Element | None) -> int:
    for node in nodes:
        if node is not None and node.sourceline:
            return int(node.sourceline)
    return 1


def make_diag(
    *,
    ctx: ModuleContext,
    path: Path | str,
    line: int,
    rule: str,
    category: str,
    tier: str,
    severity: str,
    confidence: str = "high",
    title: str,
    message: str,
    help: str,
) -> Diagnostic:
    return Diagnostic(
        module=ctx.name,
        file_path=str(path),
        line=line,
        column=0,
        rule=rule,
        category=category,
        severity=severity,
        tier=tier,
        source="native",
        confidence=confidence,
        title=title,
        message=message,
        help=help,
        odoo_version=ctx.odoo_version,
    )
