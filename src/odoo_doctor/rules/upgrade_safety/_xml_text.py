# src/odoo_doctor/rules/upgrade_safety/_xml_text.py
"""Text-level XML helpers for the migration fixers.

A fixer must not parse and serialize a data file (that would reformat it), so it edits
the text. These helpers find tags and ``<record>`` spans in the text, skipping comments,
CDATA sections and processing instructions, and edit single tags. Every offset is an
index into the text as given, so CRLF files work unchanged.

lxml reports ``sourceline`` of an element as the line where its *start tag ends* (a tag
spread over three lines is on the third), so use :func:`tags_ending_on_line` to find the
tag of a finding, not the line a tag starts on.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

_TOKEN = re.compile(
    r"""
      <!--.*?-->
    | <!\[CDATA\[.*?\]\]>
    | <\?.*?\?>
    | <!(?!--)[^>]*>
    | <(?P<close>/)?(?P<name>[\w:.-]+)(?P<attrs>(?:"[^"]*"|'[^']*'|[^>"'])*?)(?P<self>/)?>
    """,
    re.DOTALL | re.VERBOSE,
)


@dataclass(frozen=True)
class Tag:
    start: int
    end: int  # exclusive
    name: str
    closing: bool
    self_closing: bool


def tags(text: str) -> Iterator[Tag]:
    """Every real start, end and empty tag, in document order."""
    for m in _TOKEN.finditer(text):
        if m.group("name") is not None:
            yield Tag(
                m.start(),
                m.end(),
                m.group("name"),
                bool(m.group("close")),
                bool(m.group("self")),
            )


def line_of_offset(text: str, offset: int) -> int:
    """1-based line number of the character at *offset*."""
    return text.count("\n", 0, offset) + 1


def record_span(text: str, line: int) -> tuple[int, int] | None:
    """``[start, end)`` of the ``<record>`` element whose lines include *line*."""
    start: int | None = None
    for tag in tags(text):
        if tag.name != "record":
            continue
        if not tag.closing:
            start = tag.start
            if tag.self_closing:
                if (
                    line_of_offset(text, tag.start)
                    <= line
                    <= line_of_offset(text, tag.end - 1)
                ):
                    return tag.start, tag.end
                start = None
        elif start is not None:
            if line_of_offset(text, start) <= line <= line_of_offset(text, tag.end - 1):
                return start, tag.end
            start = None
    return None


def start_tags(text: str, name: str) -> list[Tag]:
    """Opening (and empty) tags called *name*, in document order."""
    return [t for t in tags(text) if t.name == name and not t.closing]


def tags_ending_on_line(text: str, line: int, name: str | None = None) -> list[Tag]:
    """Opening tags whose ``>`` is on *line*: where lxml says an element is."""
    return [
        t
        for t in tags(text)
        if not t.closing
        and (name is None or t.name == name)
        and line_of_offset(text, t.end - 1) == line
    ]


def end_tag_for(text: str, tag: Tag) -> Tag | None:
    """The closing tag matching the opening *tag* (None for an empty tag)."""
    if tag.self_closing:
        return None
    depth = 0
    for t in tags(text[tag.start :]):
        if t.name != tag.name or t.self_closing:
            continue
        depth += -1 if t.closing else 1
        if depth == 0:
            return Tag(tag.start + t.start, tag.start + t.end, t.name, True, False)
    return None


_ATTR = re.compile(
    r"""(?P<space>\s+)(?P<name>[\w:.-]+)(?P<eq>\s*=\s*)(?P<q>["'])(?P<value>.*?)(?P=q)""",
    re.DOTALL,
)


def _find_attr(tag_text: str, attr: str) -> re.Match[str] | None:
    """Match of ``attr="…"`` among the real attributes (a look-alike inside another
    attribute's value is never matched, because quoted values are consumed whole)."""
    head = re.match(r"<[\w:.-]+", tag_text)
    return next(
        (
            m
            for m in _ATTR.finditer(tag_text, head.end() if head else 0)
            if m.group("name") == attr
        ),
        None,
    )


def remove_attr(tag_text: str, attr: str) -> str:
    """Drop ``attr="…"`` and the whitespace before it; the other attributes stay as they were."""
    m = _find_attr(tag_text, attr)
    return tag_text if m is None else tag_text[: m.start()] + tag_text[m.end() :]


def rename_attr_value(tag_text: str, attr: str, old: str, new: str) -> str:
    """Change ``attr="old"`` to ``attr="new"`` (either quote style); other values stay."""
    m = _find_attr(tag_text, attr)
    if m is None or m.group("value") != old:
        return tag_text
    q = m.group("q")
    replaced = f"{m.group('space')}{attr}{m.group('eq')}{q}{new}{q}"
    return tag_text[: m.start()] + replaced + tag_text[m.end() :]


def get_attr(tag_text: str, attr: str) -> str | None:
    """Raw (still escaped) value of ``attr`` in the tag text, or None."""
    m = _find_attr(tag_text, attr)
    return None if m is None else m.group("value")


def set_attr_value(tag_text: str, attr: str, new: str) -> str:
    """Replace the raw value of ``attr`` (keeps quotes and spacing); no-op if absent."""
    m = _find_attr(tag_text, attr)
    if m is None:
        return tag_text
    q = m.group("q")
    replaced = f"{m.group('space')}{attr}{m.group('eq')}{q}{new}{q}"
    return tag_text[: m.start()] + replaced + tag_text[m.end() :]
