"""Diagnostic and text-edit conversion for the language server."""

from __future__ import annotations

import pytest

pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp  # noqa: E402

from odoo_doctor.core.diagnostics import Diagnostic  # noqa: E402
from odoo_doctor.lsp.convert import (  # noqa: E402
    diff_edits,
    split_lines,
    to_lsp_diagnostic,
)


def _diag(**over) -> Diagnostic:
    base = dict(
        module="m",
        file_path="/x/m/models/a.py",
        line=3,
        column=0,
        rule="eval-usage",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="eval() on user data",
        message="Do not use eval.",
        help="Use ast.literal_eval.",
        odoo_version="17.0",
        url="https://example.test/rules#eval-usage",
    )
    base.update(over)
    return Diagnostic(**base)


def apply_edits(text: str, edits: list[lsp.TextEdit]) -> str:
    """Apply LSP edits (all line based) to *text*, the way an editor would."""
    lines = split_lines(text)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(pos: lsp.Position) -> int:
        return starts[pos.line] + pos.character

    for edit in sorted(edits, key=lambda e: offset(e.range.start), reverse=True):
        text = (
            text[: offset(edit.range.start)]
            + edit.new_text
            + text[offset(edit.range.end) :]
        )
    return text


# --- diagnostics -------------------------------------------------------------


def test_range_covers_the_code_on_the_line_not_its_indentation():
    d = to_lsp_diagnostic(_diag(line=3), "        eval(x)\n")
    assert d.range.start == lsp.Position(line=2, character=8)
    assert d.range.end == lsp.Position(line=2, character=15)


def test_fields_are_mapped():
    d = to_lsp_diagnostic(_diag(), "eval(x)")
    assert d.severity == lsp.DiagnosticSeverity.Error
    assert d.code == "eval-usage"
    assert d.source == "odoo-doctor"
    assert d.code_description.href == "https://example.test/rules#eval-usage"
    assert "Do not use eval." in d.message
    assert d.data == {"rule": "eval-usage", "fixable": False}


@pytest.mark.parametrize(
    "severity, expected",
    [
        ("error", lsp.DiagnosticSeverity.Error),
        ("warning", lsp.DiagnosticSeverity.Warning),
        ("info", lsp.DiagnosticSeverity.Information),
        ("something-else", lsp.DiagnosticSeverity.Information),
    ],
)
def test_severity_mapping(severity: str, expected: lsp.DiagnosticSeverity):
    assert to_lsp_diagnostic(_diag(severity=severity), "x").severity == expected


def test_no_url_means_no_code_description():
    assert to_lsp_diagnostic(_diag(url=None), "x").code_description is None


def test_unknown_line_text_gives_an_empty_range_at_the_line_start():
    d = to_lsp_diagnostic(_diag(line=5), None)
    assert d.range.start == lsp.Position(line=4, character=0)
    assert d.range.end == lsp.Position(line=4, character=0)


def test_line_zero_is_clamped_to_the_first_line():
    d = to_lsp_diagnostic(_diag(line=0), "{'name': 'x'}\n")
    assert d.range.start.line == 0


def test_blank_line_text_gives_an_empty_range():
    d = to_lsp_diagnostic(_diag(line=2), "   \n")
    assert d.range.start == d.range.end == lsp.Position(line=1, character=0)


def test_fixable_flag_goes_into_data():
    d = to_lsp_diagnostic(_diag(), "x", fixable=True)
    assert d.data["fixable"] is True


# --- minimal text edits -----------------------------------------------------


@pytest.mark.parametrize(
    "old, new",
    [
        ("a\nb\nc\n", "a\nB\nc\n"),  # replace one line
        ("a\nc\n", "a\nb\nc\n"),  # insert
        ("a\nb\nc\n", "a\nc\n"),  # delete
        ("a\nb\nc\n", "a\nb\nc\nd\n"),  # append at EOF
        ("a\nb", "a\nB"),  # no trailing newline, change last line
        ("a\nb", "a\nb\nc"),  # no trailing newline, append
        ("", "x\n"),  # empty document
        ("a\nb\n", ""),  # clear the document
        ("keep\n", "keep\n"),  # unchanged
    ],
)
def test_diff_edits_reproduce_the_new_text(old: str, new: str):
    assert apply_edits(old, diff_edits(old, new)) == new


def test_unchanged_text_needs_no_edit():
    assert diff_edits("a\nb\n", "a\nb\n") == []


def test_edits_touch_only_the_changed_lines():
    edits = diff_edits("a\nb\nc\nd\n", "a\nb\nC\nd\n")
    assert len(edits) == 1
    assert edits[0].range.start.line == 2 and edits[0].range.end.line == 3


# --- line splitting follows Python / LSP, not str.splitlines ------------------


def test_split_lines_only_breaks_on_real_line_endings():
    assert split_lines("a\x0cb\nc\r\nd\re") == ["a\x0cb\n", "c\r\n", "d\r", "e"]
    assert split_lines("") == []
    assert split_lines("x\n") == ["x\n"]


def test_diff_edits_are_not_confused_by_form_feeds():
    old = "a\x0cb\nc\n"
    new = "a\x0cb\nC\n"
    edits = diff_edits(old, new)
    assert len(edits) == 1 and edits[0].range.start.line == 1
