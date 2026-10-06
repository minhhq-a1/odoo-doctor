"""sudo-without-comment flags .sudo() calls lacking a justifying comment."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.security.sudo_without_comment import (
    check_sudo_without_comment,
)


def _write(tmp_path: Path, src: str) -> Path:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return f


def test_sudo_without_comment_is_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self):
                return self.env["x"].sudo().search([])
        """,
    )
    diags = check_sudo_without_comment(f, "m", "17.0")
    assert any(d.rule == "sudo-without-comment" for d in diags)


def test_sudo_with_inline_comment_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self):
                return self.env["x"].sudo().search([])  # sudo: cron has no user
        """,
    )
    diags = check_sudo_without_comment(f, "m", "17.0")
    assert not any(d.rule == "sudo-without-comment" for d in diags)


def test_sudo_with_comment_above_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self):
                # sudo needed: runs in cron context without a user
                return self.env["x"].sudo().search([])
        """,
    )
    diags = check_sudo_without_comment(f, "m", "17.0")
    assert not any(d.rule == "sudo-without-comment" for d in diags)


def _flagged_lines(tmp_path: Path, src: str, name: str = "m.py") -> list[int]:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(src))
    return [d.line for d in check_sudo_without_comment(f, "m", "17.0")]


def test_comment_above_a_multiline_statement_justifies_the_sudo(tmp_path: Path):
    """The call starts on the first line of a chain; the sudo sits on a later one."""
    src = """\
        class M:
            def f(self):
                # portal users cannot read the parameter
                value = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("k")
                )
                return value
        """
    assert _flagged_lines(tmp_path, src) == []


def test_comment_on_a_continuation_line_justifies_the_sudo(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                return self.env["x"].search(
                    [("a", "=", 1)]  # only the rows of the current company
                ).sudo()
        """
    assert _flagged_lines(tmp_path, src) == []


def test_comment_above_a_compound_statement_header_justifies_it(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                # the portal user cannot see other partners' orders
                if self.env["x"].sudo().search([]):
                    return 1
        """
    assert _flagged_lines(tmp_path, src) == []


def test_comment_inside_a_compound_body_does_not_justify_the_header(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                if self.env["x"].sudo().search([]):
                    # unrelated remark about the branch
                    return 1
        """
    assert _flagged_lines(tmp_path, src) == [3]


def test_sudo_false_drops_privileges_and_is_not_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                return self.sudo(False).env["x"].search([])
        """
    assert _flagged_lines(tmp_path, src) == []


def test_sudo_with_a_user_or_flag_is_still_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, flag):
                self.sudo(flag).read()
        """
    assert _flagged_lines(tmp_path, src) == [3]


def test_test_and_migration_files_are_skipped(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                return self.env["x"].sudo().search([])
        """
    assert _flagged_lines(tmp_path, src, "m/tests/test_x.py") == []
    assert _flagged_lines(tmp_path, src, "m/migrations/17.0.1.0/post-x.py") == []
    assert _flagged_lines(tmp_path, src, "m/models/x.py") == [3]


def test_finding_is_low_confidence(tmp_path: Path):
    """A comment per sudo() is a team convention (most of Odoo's own code ignores it),
    so a surface with min_confidence = "medium" must be able to hide it."""
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self):
                return self.env["x"].sudo().search([])
        """,
    )
    (diag,) = check_sudo_without_comment(f, "m", "17.0")
    assert diag.confidence == "low"
    meta, _ = default_registry.get("sudo-without-comment")
    assert meta.default_confidence == "low"
