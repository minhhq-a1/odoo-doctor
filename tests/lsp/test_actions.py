"""Code actions: quick fix, disable on a line / in a file / in the config."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp
from lxml import etree

import odoo_doctor.cli.app  # noqa: F401  (registers rules and fixers)
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.lsp.actions import (
    code_actions_for,
    disable_file_edit,
    disable_line_edit,
    fix_edits,
)
from odoo_doctor.lsp.convert import to_lsp_diagnostic
from odoo_doctor.rules.suppression import (
    scan_python_suppressions,
    scan_xml_suppressions,
)
from tests.lsp.test_convert import apply_edits


def _finding(path: Path, rule: str = "eval-usage", line: int = 3, **over) -> Diagnostic:
    base = {
        "module": "m",
        "file_path": str(path),
        "line": line,
        "column": 0,
        "rule": rule,
        "category": "Security",
        "severity": "error",
        "tier": "P0",
        "source": "native",
        "confidence": "high",
        "title": "t",
        "message": "msg",
        "help": "h",
        "odoo_version": "17.0",
        "url": "https://example.test/x",
    }
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


# --- review fixes: never insert a comment where it breaks the code -----------


def test_no_disable_line_inside_a_multiline_string(tmp_path: Path):
    text = 'q = """\nSELECT 1\nFROM t\n"""\nx = 1\n'
    assert disable_line_edit("r", str(tmp_path / "a.py"), 3, text) is None
    assert disable_line_edit("r", str(tmp_path / "a.py"), 5, text) is not None


def test_no_disable_line_after_a_backslash_continuation(tmp_path: Path):
    text = "total = 1 + \\\n    2\nx = 1\n"
    assert disable_line_edit("r", str(tmp_path / "a.py"), 2, text) is None
    assert disable_line_edit("r", str(tmp_path / "a.py"), 3, text) is not None


def test_disable_line_is_fine_between_bracketed_arguments(tmp_path: Path):
    f = tmp_path / "a.py"
    text = "call(\n    1,\n    2,\n)\n"
    edit = disable_line_edit("r", str(f), 3, text)
    assert edit is not None
    new = apply_edits(text, [edit])
    compile(new, "a.py", "exec")  # still valid Python


def test_no_disable_line_when_python_cannot_be_tokenized(tmp_path: Path):
    assert disable_line_edit("r", str(tmp_path / "a.py"), 2, "x = (\ny = 1\n") is None


def test_form_feed_does_not_shift_the_target_line(tmp_path: Path):
    text = "a = 1 \x0c b = 2\nprint(x)\n"
    edit = disable_line_edit("r", str(tmp_path / "a.py"), 2, text)
    assert apply_edits(text, [edit]) == (
        "a = 1 \x0c b = 2\n# odoo-doctor: disable=r\nprint(x)\n"
    )


def test_no_disable_line_on_xml_continuation_or_declaration(tmp_path: Path):
    f = str(tmp_path / "v.xml")
    text = '<?xml version="1.0"?>\n<odoo>\n  <record\n      id="x"/>\n</odoo>\n'
    assert disable_line_edit("r", f, 1, text) is None  # before the declaration
    assert disable_line_edit("r", f, 4, text) is None  # inside a tag
    assert disable_line_edit("r", f, 3, text) is not None


def test_crlf_files_keep_their_line_endings(tmp_path: Path):
    f = str(tmp_path / "a.py")
    text = "def f():\r\n    eval(x)\r\n"
    new = apply_edits(text, [disable_line_edit("r", f, 2, text)])
    assert new == "def f():\r\n    # odoo-doctor: disable=r\r\n    eval(x)\r\n"
    merged = apply_edits(new, [disable_line_edit("s", f, 3, new)])
    assert "disable=r,s\r\n" in merged and "\n" not in merged.replace("\r\n", "")
    top = apply_edits(text, [disable_file_edit("r", f, text)])
    assert top.startswith("# odoo-doctor: disable-file=r\r\n")


# --- stale buffers -------------------------------------------------------------


def test_line_in_sync_compares_the_buffer_line_with_the_disk_line():
    from odoo_doctor.lsp.actions import line_in_sync

    disk = "a\nb\nc\n"
    assert line_in_sync(2, "a\nb\nc\n", disk)
    assert line_in_sync(2, "a\nb\nX\n", disk)  # edits elsewhere do not matter
    assert not line_in_sync(2, "new\na\nb\nc\n", disk)  # lines inserted above
    assert not line_in_sync(2, "a\nB\nc\n", disk)  # the flagged line itself changed
    assert not line_in_sync(9, disk, disk)
    assert not line_in_sync(2, disk, None)
    assert line_in_sync(0, "a\nb\n", "a\nb\n")  # module-level findings use line 1


def test_a_stale_buffer_only_keeps_the_actions_that_do_not_depend_on_the_line(
    tmp_path: Path,
):
    f = tmp_path / "__manifest__.py"
    finding = _finding(f, rule="manifest-missing-required-fields", line=1)
    actions = code_actions_for(
        finding,
        MANIFEST,
        f.as_uri(),
        to_lsp_diagnostic(finding, MANIFEST),
        in_sync=False,
    )
    assert _titles(actions) == [
        "Odoo Doctor: disable manifest-missing-required-fields in this file",
        "Odoo Doctor: disable manifest-missing-required-fields in odoo-doctor.toml",
    ]
