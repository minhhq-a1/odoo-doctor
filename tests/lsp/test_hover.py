"""Hover: the rule explanation from RULE_DOCS, for the finding under the cursor."""

from __future__ import annotations

import pytest

pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.lsp.hover import hover_for
from odoo_doctor.rules.rule_docs import RULE_DOCS, RuleDoc

LINE_TEXT = "        eval(user_input)\n"  # code spans characters 8..24


def _diag(**over) -> Diagnostic:
    base = {
        "module": "m",
        "file_path": "/x/m/models/a.py",
        "line": 3,
        "column": 0,
        "rule": "eval-usage",
        "category": "Security",
        "severity": "error",
        "tier": "P0",
        "source": "native",
        "confidence": "high",
        "title": "eval() on user data",
        "message": "Do not use eval on user data.",
        "help": "Use ast.literal_eval.",
        "odoo_version": "17.0",
        "url": "https://example.test/rules#eval-usage",
    }
    base.update(over)
    return Diagnostic(**base)


def _at(character: int, line: int = 2) -> lsp.Position:
    return lsp.Position(line=line, character=character)


def _text(result: lsp.Hover | None) -> str:
    assert result is not None
    assert isinstance(result.contents, lsp.MarkupContent)
    assert result.contents.kind == lsp.MarkupKind.Markdown
    return result.contents.value


def test_hover_explains_a_native_rule():
    doc = RULE_DOCS["eval-usage"]
    text = _text(hover_for([_diag()], _at(12), LINE_TEXT))
    assert "eval-usage" in text
    assert "P0" in text and "error" in text and "high" in text
    assert doc.detects in text and doc.why in text and doc.fix in text
    assert doc.bad in text and doc.good in text
    assert "```python" in text
    assert "https://example.test/rules#eval-usage" in text


def test_hover_does_not_repeat_the_diagnostic_message():
    # the editor already shows message and help from the diagnostic itself
    text = _text(hover_for([_diag()], _at(12), LINE_TEXT))
    assert "Do not use eval on user data." not in text
    assert "Use ast.literal_eval." not in text


def test_hover_range_is_the_code_span_of_the_line():
    result = hover_for([_diag()], _at(12), LINE_TEXT)
    assert result.range == lsp.Range(
        start=lsp.Position(line=2, character=8),
        end=lsp.Position(line=2, character=24),
    )


@pytest.mark.parametrize(
    "position",
    [_at(12, line=1), _at(12, line=3), _at(2), _at(40)],
    ids=["line above", "line below", "in the indentation", "past the end"],
)
def test_no_hover_off_the_flagged_code(position):
    assert hover_for([_diag()], position, LINE_TEXT) is None


def test_no_hover_without_findings():
    assert hover_for([], _at(12), LINE_TEXT) is None


def test_two_findings_on_one_line_are_both_explained():
    findings = [_diag(), _diag(rule="raw-sql-string-interpolation", tier="P1")]
    text = _text(hover_for(findings, _at(12), LINE_TEXT))
    assert "eval-usage" in text and "raw-sql-string-interpolation" in text
    assert RULE_DOCS["raw-sql-string-interpolation"].detects in text


def test_external_finding_without_docs_falls_back_to_its_own_text():
    ruff = _diag(
        rule="F401",
        source="ruff",
        severity="warning",
        tier="P3",
        title="Unused import",
        message="`os` imported but unused",
        help="Remove the import",
        url="",
    )
    text = _text(hover_for([ruff], _at(12), LINE_TEXT))
    assert "F401" in text and "ruff" in text
    assert "Unused import" in text and "Remove the import" in text


@pytest.mark.parametrize("name", sorted(RULE_DOCS))
def test_every_documented_rule_renders(name):
    text = _text(hover_for([_diag(rule=name)], _at(12), LINE_TEXT))
    assert RULE_DOCS[name].detects in text


def test_empty_sections_are_left_out(monkeypatch):
    monkeypatch.setitem(RULE_DOCS, "only-detects", RuleDoc(detects="What it finds."))
    text = _text(hover_for([_diag(rule="only-detects")], _at(12), LINE_TEXT))
    assert "What it finds." in text
    for heading in ("Why", "Fix", "Bad", "Good", "```"):
        assert heading not in text


def test_a_code_sample_cannot_close_its_own_fence(monkeypatch):
    monkeypatch.setitem(
        RULE_DOCS,
        "fence",
        RuleDoc(detects="d", bad="x = '```'", good="y = 1"),
    )
    text = _text(hover_for([_diag(rule="fence")], _at(12), LINE_TEXT))
    longest_open = max(
        len(line) - len(line.lstrip("`"))
        for line in text.splitlines()
        if line.startswith("```") and line.strip("`").strip() in ("python", "")
    )
    assert longest_open >= 4  # longer than the ``` inside the sample
