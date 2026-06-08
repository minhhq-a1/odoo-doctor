from pathlib import Path
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.reporters.github_annotations import (
    render_github_annotations,
)


def test_renders_error_annotation():
    d = Diagnostic(
        module="my_addon",
        file_path="/repo/my_addon/models.py",
        line=10,
        column=5,
        rule="some-rule",
        category="Correctness",
        severity="error",
        tier="P1",
        source="native",
        confidence="high",
        title="Bad Code",
        message="This is bad.",
        help="Fix it.",
        odoo_version="17.0",
    )
    result = render_github_annotations([d], Path("/repo"))
    assert (
        result.strip()
        == "::error file=my_addon/models.py,line=10,col=5,title=Bad Code::This is bad."
    )


def test_severity_maps_to_level():
    d1 = Diagnostic(
        "m",
        "/repo/a.py",
        1,
        1,
        "r",
        "c",
        "warning",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )
    d2 = Diagnostic(
        "m",
        "/repo/b.py",
        1,
        1,
        "r",
        "c",
        "info",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )

    res = render_github_annotations([d1, d2], Path("/repo"))
    assert "::warning file=a.py,line=1,col=1,title=t::m" in res
    assert "::notice file=b.py,line=1,col=1,title=t::m" in res


def test_message_special_chars_escaped():
    # Message: \n, %, \r
    # Title: , :
    d = Diagnostic(
        module="m",
        file_path="/repo/a.py",
        line=1,
        column=1,
        rule="r",
        category="c",
        severity="error",
        tier="P1",
        source="s",
        confidence="high",
        title="Title, with: colon",
        message="Line 1\nLine 2\r100%",
        help="h",
        odoo_version="17",
    )
    res = render_github_annotations([d], Path("/repo"))
    # %25 should be first, but since _escape replaces %, it must replace % first.
    assert (
        "::error file=a.py,line=1,col=1,title=Title%2C with%3A colon::Line 1%0ALine 2%0D100%25"
        in res
    )


def test_path_relativized_to_repo_root():
    d = Diagnostic(
        "m",
        "/repo/subdir/a.py",
        1,
        1,
        "r",
        "c",
        "error",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )
    res = render_github_annotations([d], Path("/repo"))
    assert "file=subdir/a.py" in res


def test_path_outside_root_falls_back_to_basename():
    d = Diagnostic(
        "m",
        "/outside/a.py",
        1,
        1,
        "r",
        "c",
        "error",
        "P1",
        "s",
        "high",
        "t",
        "m",
        "h",
        "17",
    )
    res = render_github_annotations([d], Path("/repo"))
    assert "file=a.py" in res
