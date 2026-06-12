"""Baseline identity is line-independent and round-trips through a file."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.baseline import (
    finding_identity,
    write_baseline,
    load_baseline,
    filter_against_baseline,
)


def _src(tmp_path: Path) -> Path:
    f = tmp_path / "x.py"
    f.write_text(
        "a = eval(x)\n"  # line 1
        "b = 2\n"  # line 2
        "c = eval(y)\n"  # line 3
    )
    return f


def _diag(file_path: str, line: int, rule: str = "eval-usage") -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path=file_path,
        line=line,
        column=0,
        rule=rule,
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="help",
        odoo_version="17.0",
    )


def test_identity_independent_of_line_position_same_content(tmp_path: Path):
    # Same file, same line content at a different line number -> same identity.
    f = tmp_path / "a.py"
    f.write_text("a = eval(x)\n")
    id_top = finding_identity(_diag(str(f), 1))
    f.write_text("\n\na = eval(x)\n")  # identical content, now line 3
    id_moved = finding_identity(_diag(str(f), 3))
    assert id_top == id_moved


def test_identity_distinguishes_two_findings_same_rule_same_file(tmp_path: Path):
    f = _src(tmp_path)
    # eval on line 1 ("eval(x)") vs line 3 ("eval(y)") must NOT collapse.
    assert finding_identity(_diag(str(f), 1)) != finding_identity(_diag(str(f), 3))


def test_identity_differs_by_rule(tmp_path: Path):
    f = _src(tmp_path)
    assert finding_identity(_diag(str(f), 1, "eval-usage")) != finding_identity(
        _diag(str(f), 1, "sudo-without-comment")
    )


def test_identity_stable_under_unrelated_edit(tmp_path: Path):
    f = _src(tmp_path)
    id_before = finding_identity(_diag(str(f), 3))  # the eval(y) finding
    # Edit an unrelated earlier line; the eval(y) line moves down but its
    # content is unchanged -> identity stays the same.
    f.write_text("a = eval(x)\nb = 2\nNEW = 0\nc = eval(y)\n")
    id_after = finding_identity(_diag(str(f), 4))
    assert id_before == id_after


def test_filter_drops_baselined_findings(tmp_path: Path):
    f = _src(tmp_path)
    bfile = tmp_path / "baseline.json"
    write_baseline([_diag(str(f), 1)], bfile)  # baseline the eval(x) finding
    ids = load_baseline(bfile)

    kept = filter_against_baseline([_diag(str(f), 1), _diag(str(f), 3)], ids)
    # eval(x) (line 1) suppressed; eval(y) (line 3) is a distinct identity, kept.
    kept_lines = {d.line for d in kept}
    assert kept_lines == {3}
