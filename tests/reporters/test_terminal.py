# tests/reporters/test_terminal.py
"""Tests for terminal reporter."""

from __future__ import annotations

import re

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.terminal import render_terminal


def _diag(**overrides) -> Diagnostic:
    defaults = {
        "module": "sale_custom",
        "file_path": "models/sale.py",
        "line": 42,
        "column": 0,
        "rule": "raw-sql",
        "category": "Security",
        "severity": "error",
        "tier": "P0",
        "source": "native",
        "confidence": "high",
        "title": "SQL injection",
        "message": "cr.execute uses f-string",
        "help": "Use params",
        "odoo_version": "17.0",
    }
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_terminal_returns_string():
    diags = [_diag()]
    score = ScoreResult(
        overall=75.0,
        label="Good",
        categories=[CategoryScore("Security", 75, 1, 25.0)],
        in_scope_categories=["Security"],
        diagnostics_counted=1,
    )
    output = render_terminal(diags, {"sale_custom": score})
    assert "sale_custom" in output
    assert "75" in output
    assert "SQL injection" in output


def test_render_terminal_empty():
    output = render_terminal([], {})
    assert "No diagnostics" in output or "clean" in output.lower()


def test_render_terminal_shows_project_score_for_multiple_modules():
    clean = ScoreResult(
        overall=100.0,
        label="Excellent",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=0,
    )
    bad = ScoreResult(
        overall=50.0,
        label="Needs work",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=2,
    )

    output = render_terminal([], {"clean": clean, "bad": bad})

    assert "Project Score:" in output
    assert "75" in output
    assert "100" in output
    assert "Good" in output


def test_render_terminal_omits_project_score_for_single_module():
    score = ScoreResult(
        overall=100.0,
        label="Excellent",
        categories=[],
        in_scope_categories=[],
        diagnostics_counted=0,
    )

    output = render_terminal([], {"clean": score})

    assert "Project Score:" not in output


def test_render_terminal_shows_top_findings_multi_module():
    d1 = _diag(module="mod_a", tier="P0", title="SQL injection in mod_a")
    d2 = _diag(module="mod_b", tier="P1", title="Missing access in mod_b")
    scores = {
        "mod_a": ScoreResult(50.0, "Needs work", [], [], 1),
        "mod_b": ScoreResult(70.0, "Needs work", [], [], 1),
    }
    output = render_terminal([d1, d2], scores)
    assert "Top Findings" in output
    assert "SQL injection in mod_a" in output


def test_render_terminal_no_top_findings_single_module():
    d1 = _diag(module="mod_a", tier="P0", title="SQL injection")
    scores = {"mod_a": ScoreResult(50.0, "Needs work", [], [], 1)}
    output = render_terminal([d1], scores)
    assert "Top Findings" not in output


def test_render_terminal_shows_one_decimal_score():
    score = ScoreResult(99.5, "Excellent", [], [], 0)
    output = render_terminal([], {"m": score})
    assert "99.5" in output


def _plain(text: str) -> str:
    """Strip ANSI and collapse whitespace so rich's line wrapping does not matter."""
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", text).split())


def _single_score() -> dict:
    return {
        "sale_custom": ScoreResult(
            overall=75.0,
            label="Good",
            categories=[CategoryScore("Security", 75, 1, 25.0)],
            in_scope_categories=["Security"],
            diagnostics_counted=1,
        )
    }


def test_confidence_marker_is_printed_literally():
    out = _plain(render_terminal([_diag(confidence="low")], _single_score()))
    assert "SQL injection [low]" in out
    out = _plain(render_terminal([_diag(confidence="medium")], _single_score()))
    assert "SQL injection [medium]" in out


def test_footer_appears_only_when_something_is_hidden():
    out = _plain(render_terminal([_diag()], _single_score()))
    assert "hidden by" not in out
    out = _plain(render_terminal([_diag()], _single_score(), hidden=3))
    assert (
        "3 finding(s) hidden by [surfaces.terminal]. Show all with --show-low." in out
    )


def test_everything_hidden_still_shows_scores_and_the_footer():
    out = _plain(render_terminal([], _single_score(), hidden=2))
    assert "sale_custom Score: 75.0/100" in out
    assert "Security" in out and "Findings for" not in out
    assert "2 finding(s) hidden by [surfaces.terminal]" in out


def test_all_clean_only_when_there_is_truly_nothing():
    assert "All clean" in render_terminal([], {})
    assert "All clean" not in render_terminal([], {}, hidden=1)


def test_text_that_looks_like_rich_markup_is_printed_literally():
    d = _diag(
        title="Odd [/x] title",
        message="closing tag [/bold] and [red]colour[/red] in message",
        help="see [/dim] here",
        url="https://example.com/[/x]",
        file_path="addons/[/m]/a.py",
    )
    out = _plain(render_terminal([d], _single_score()))
    assert "Odd [/x] title" in out
    assert "closing tag [/bold] and [red]colour[/red] in message" in out
    assert "see [/dim] here" in out
    assert "https://example.com/[/x]" in out
    assert "addons/[/m]/a.py" in out


def test_render_terminal_shows_secondary_scores_when_they_differ():
    a = ScoreResult(
        100.0, "Excellent", [], [], 0, python_lines=300, overall_with_medium=100.0
    )
    b = ScoreResult(80.0, "Good", [], [], 1, python_lines=100, overall_with_medium=60.0)
    output = render_terminal([], {"a": a, "b": b})
    assert "Weighted by code size: 95.0" in output
    assert "Counting medium findings: 80.0" in output


def test_render_terminal_hides_secondary_scores_when_equal():
    a = ScoreResult(100.0, "Excellent", [], [], 0)
    b = ScoreResult(100.0, "Excellent", [], [], 0)
    assert "Weighted" not in render_terminal([], {"a": a, "b": b})


def test_render_terminal_shows_a_difference_of_exactly_one_tenth():
    # 90.0 vs 89.9 is 0.0999... as a float but a displayed difference of 0.1
    a = ScoreResult(90.0, "Excellent", [], [], 0, overall_with_medium=89.9)
    b = ScoreResult(90.0, "Excellent", [], [], 0, overall_with_medium=89.9)
    assert "Counting medium findings: 89.9" in render_terminal([], {"a": a, "b": b})


def test_hostile_names_cannot_start_a_workflow_command_line():
    """CI logs are parsed for lines starting with `::`; a newline in a repo-chosen
    name must not be able to start one, nor may a raw ESC reach the terminal."""
    hostile = "a\n::error::boom\x1b[2J.py"
    d = _diag(
        module="m\n::error::mod",
        file_path=hostile,
        title="t\n::error::title",
        message="msg\n::error::msg",
    )
    score = ScoreResult(50.0, "Needs work", [], [d], 1)
    out = render_terminal([d], {d.module: score})
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)  # rich's own styling
    assert "\x1b" not in plain
    assert not [line for line in plain.splitlines() if line.lstrip().startswith("::")]
    assert "\\n::error::boom" in plain  # still visible, as text
