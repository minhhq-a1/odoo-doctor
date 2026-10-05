"""Code actions: quick fix, disable on a line / in a file / in the config."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp  # noqa: E402
from lxml import etree  # noqa: E402

import odoo_doctor.cli.app  # noqa: E402,F401  (registers rules and fixers)
from odoo_doctor.core.diagnostics import Diagnostic  # noqa: E402
from odoo_doctor.lsp.actions import (  # noqa: E402
    code_actions_for,
    disable_file_edit,
    disable_line_edit,
    fix_edits,
)
from odoo_doctor.lsp.convert import to_lsp_diagnostic  # noqa: E402
from odoo_doctor.rules.suppression import (  # noqa: E402
    scan_python_suppressions,
    scan_xml_suppressions,
)
from tests.lsp.test_convert import apply_edits  # noqa: E402


def _finding(path: Path, rule: str = "eval-usage", line: int = 3, **over) -> Diagnostic:
    base = dict(
        module="m",
        file_path=str(path),
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
        help="h",
        odoo_version="17.0",
        url="https://example.test/x",
    )
    base.update(over)
    return Diagnostic(**base)


PY = "class A:\n    def f(self):\n        eval(x)\n"


# --- disable on this line -----------------------------------------------------


def test_disable_line_inserts_an_indented_comment_that_really_suppresses(
    tmp_path: Path,
):
    f = tmp_path / "a.py"
    edit = disable_line_edit("eval-usage", str(f), 3, PY)
    new = apply_edits(PY, [edit])
    assert new.splitlines()[2] == "        # odoo-doctor: disable=eval-usage"
    assert new.splitlines()[3] == "        eval(x)"
    f.write_text(new)
    # the finding moved to line 4; the comment on line 3 must cover it
    assert (str(f), 4, "eval-usage") in scan_python_suppressions(f)


def test_disable_line_merges_into_an_existing_disable_comment(tmp_path: Path):
    f = tmp_path / "a.py"
    text = "def f():\n    # odoo-doctor: disable=other-rule\n    eval(x)\n"
    edit = disable_line_edit("eval-usage", str(f), 3, text)
    new = apply_edits(text, [edit])
    assert new.count("odoo-doctor: disable=") == 1  # stacked comments would not work
    f.write_text(new)
    found = scan_python_suppressions(f)
    assert (str(f), 3, "other-rule") in found
    assert (str(f), 3, "eval-usage") in found


def test_disable_line_is_none_when_the_rule_is_already_disabled(tmp_path: Path):
    text = "def f():\n    # odoo-doctor: disable=eval-usage\n    eval(x)\n"
    assert disable_line_edit("eval-usage", str(tmp_path / "a.py"), 3, text) is None


def test_disable_line_in_xml_uses_an_xml_comment(tmp_path: Path):
    f = tmp_path / "v.xml"
    text = '<odoo>\n  <record id="x"/>\n</odoo>\n'
    edit = disable_line_edit("duplicate-xml-id", str(f), 2, text)
    new = apply_edits(text, [edit])
    assert new.splitlines()[1] == "  <!-- odoo-doctor: disable=duplicate-xml-id -->"
    f.write_text(new)
    etree.parse(str(f))  # still well formed
    assert (str(f), 3, "duplicate-xml-id") in scan_xml_suppressions(f)


@pytest.mark.parametrize("name, line", [("data.csv", 2), ("a.py", 0), ("a.py", 99)])
def test_disable_line_is_unavailable_where_it_cannot_work(
    tmp_path: Path, name: str, line: int
):
    assert disable_line_edit("r", str(tmp_path / name), line, PY) is None


# --- disable in this file ----------------------------------------------------


def test_disable_file_goes_first_and_suppresses_the_whole_file(tmp_path: Path):
    f = tmp_path / "a.py"
    new = apply_edits(PY, [disable_file_edit("eval-usage", str(f), PY)])
    assert new.splitlines()[0] == "# odoo-doctor: disable-file=eval-usage"
    f.write_text(new)
    assert (str(f), 0, "eval-usage") in scan_python_suppressions(f)


def test_disable_file_keeps_a_shebang_first(tmp_path: Path):
    text = "#!/usr/bin/env python\nx = 1\n"
    new = apply_edits(text, [disable_file_edit("r", str(tmp_path / "a.py"), text)])
    assert new.splitlines()[0] == "#!/usr/bin/env python"
    assert new.splitlines()[1] == "# odoo-doctor: disable-file=r"


def test_disable_file_in_xml_goes_after_the_declaration(tmp_path: Path):
    f = tmp_path / "v.xml"
    text = '<?xml version="1.0" encoding="utf-8"?>\n<odoo/>\n'
    new = apply_edits(text, [disable_file_edit("r", str(f), text)])
    assert new.splitlines()[0].startswith("<?xml")
    assert new.splitlines()[1] == "<!-- odoo-doctor: disable-file=r -->"
    f.write_text(new)
    etree.parse(str(f))
    assert (str(f), 0, "r") in scan_xml_suppressions(f)


def test_disable_file_is_unavailable_for_other_file_types(tmp_path: Path):
    assert disable_file_edit("r", str(tmp_path / "data.csv"), "a,b\n") is None


# --- quick fix ---------------------------------------------------------------

MANIFEST = "{'name': 'X', 'version': '1.0', 'depends': ['base'], 'data': []}\n"


def test_fix_edits_use_the_deterministic_fixer(tmp_path: Path):
    f = tmp_path / "__manifest__.py"
    finding = _finding(f, rule="manifest-missing-required-fields", line=1)
    edits = fix_edits(finding, MANIFEST)
    assert edits
    assert "license" in apply_edits(MANIFEST, edits)


def test_fix_edits_none_for_a_rule_without_a_fixer(tmp_path: Path):
    assert fix_edits(_finding(tmp_path / "a.py"), PY) is None


def test_fix_edits_none_for_low_confidence(tmp_path: Path):
    finding = _finding(
        tmp_path / "__manifest__.py",
        rule="manifest-missing-required-fields",
        line=1,
        confidence="medium",
    )
    assert fix_edits(finding, MANIFEST) is None


# --- the action list -----------------------------------------------------------


def _titles(actions) -> list[str]:
    return [a.title for a in actions]


def test_actions_for_a_python_finding_without_a_fixer(tmp_path: Path):
    f = tmp_path / "a.py"
    finding = _finding(f)
    actions = code_actions_for(
        finding, PY, f.as_uri(), to_lsp_diagnostic(finding, "eval(x)")
    )
    assert _titles(actions) == [
        "Odoo Doctor: disable eval-usage on this line",
        "Odoo Doctor: disable eval-usage in this file",
        "Odoo Doctor: disable eval-usage in odoo-doctor.toml",
    ]
    assert all(a.kind == lsp.CodeActionKind.QuickFix for a in actions)
    assert actions[0].edit.changes[f.as_uri()]
    command = actions[2].command
    assert command.command == "odooDoctor.disableRule"
    assert command.arguments == ["eval-usage", f.as_uri()]


def test_a_fixable_finding_gets_the_fix_first_and_preferred(tmp_path: Path):
    f = tmp_path / "__manifest__.py"
    finding = _finding(f, rule="manifest-missing-required-fields", line=1)
    actions = code_actions_for(
        finding, MANIFEST, f.as_uri(), to_lsp_diagnostic(finding, MANIFEST)
    )
    assert actions[0].title == "Odoo Doctor: fix manifest-missing-required-fields"
    assert actions[0].is_preferred is True
    assert len(actions) == 4


def test_a_csv_finding_can_only_be_disabled_in_the_config(tmp_path: Path):
    f = tmp_path / "ir.model.access.csv"
    finding = _finding(f, rule="missing-access-csv", line=2)
    actions = code_actions_for(
        finding, "a,b\n", f.as_uri(), to_lsp_diagnostic(finding, "a,b")
    )
    assert _titles(actions) == [
        "Odoo Doctor: disable missing-access-csv in odoo-doctor.toml"
    ]
