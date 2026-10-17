"""Baseline identity is line-independent and round-trips through a file."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.baseline import (
    filter_against_baseline,
    finding_identity,
    load_baseline,
    write_baseline,
)
from odoo_doctor.core.diagnostics import Diagnostic


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


def _manifest_diag(path: Path, title: str, confidence: str = "medium") -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path=str(path),
        line=1,
        column=0,
        rule="manifest-missing-required-fields",
        category="Module Hygiene",
        severity="error",
        tier="P2",
        source="native",
        confidence=confidence,
        title=title,
        message="msg",
        help="help",
        odoo_version="17.0",
    )


def test_same_rule_same_line_findings_have_separate_identities(tmp_path: Path):
    mf = tmp_path / "__manifest__.py"
    mf.write_text("{'name': 'x'}\n")
    version = _manifest_diag(mf, "Manifest missing required field: 'version'")
    lic = _manifest_diag(mf, "Manifest missing required field: 'license'", "high")
    assert finding_identity(version) != finding_identity(lic)


def test_baselined_medium_does_not_hide_later_high_at_same_line(tmp_path: Path):
    mf = tmp_path / "__manifest__.py"
    mf.write_text("{'name': 'x'}\n")
    version = _manifest_diag(mf, "Manifest missing required field: 'version'")
    lic = _manifest_diag(mf, "Manifest missing required field: 'license'", "high")
    bfile = tmp_path / "b.json"
    write_baseline([version], bfile)
    assert filter_against_baseline([version, lic], load_baseline(bfile)) == [lic]


def test_write_baseline_writes_version_2(tmp_path: Path):
    import json

    bfile = tmp_path / "b.json"
    write_baseline([_diag(str(_src(tmp_path)), 1)], bfile)
    assert json.loads(bfile.read_text())["version"] == 2


def _v1_identity(diag: Diagnostic) -> str:
    import hashlib

    from odoo_doctor.core.baseline import _snippet

    key = f"{diag.rule}\0{diag.module}\0{diag.file_path}\0{_snippet(diag)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def test_version_1_file_still_suppresses_by_old_identity(tmp_path: Path):
    import json

    f = _src(tmp_path)
    d = _diag(str(f), 1)
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps({"version": 1, "ids": [_v1_identity(d)]}))
    assert filter_against_baseline([d, _diag(str(f), 3)], load_baseline(bfile)) == [
        _diag(str(f), 3)
    ]


def test_version_1_file_with_several_same_line_findings_suppresses_all(
    tmp_path: Path,
):
    import json

    mf = tmp_path / "__manifest__.py"
    mf.write_text("{'name': 'x'}\n")
    a = _manifest_diag(mf, "Manifest missing required field: 'version'")
    b = _manifest_diag(mf, "Manifest missing required field: 'license'", "high")
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps({"version": 1, "ids": [_v1_identity(a)]}))
    assert filter_against_baseline([a, b], load_baseline(bfile)) == []


def test_version_2_file_ignores_old_style_identities(tmp_path: Path):
    import json

    mf = tmp_path / "__manifest__.py"
    mf.write_text("{'name': 'x'}\n")
    a = _manifest_diag(mf, "Manifest missing required field: 'version'")
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps({"version": 2, "ids": [_v1_identity(a)]}))
    assert filter_against_baseline([a], load_baseline(bfile)) == [a]


def test_garbage_baseline_is_empty(tmp_path: Path):
    bfile = tmp_path / "b.json"
    bfile.write_text("[1, 2]")
    assert filter_against_baseline([], load_baseline(bfile)) == []
    bfile.write_text("not json")
    assert len(load_baseline(bfile)) == 0
