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


def _lines(tmp_path: Path, src: str) -> list[int]:
    return [
        d.line for d in check_sudo_without_comment(_write(tmp_path, src), "m", "17.0")
    ]


def test_a_comment_naming_sudo_a_few_lines_above_justifies_it(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                # We do sudo because the closing user may lack access.
                a = 1
                b = 2
                return self.env["x"].sudo().search([]), a, b
        """
    assert _lines(tmp_path, src) == []


def test_a_comment_naming_sudo_far_above_does_not(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                # sudo is needed here
                a = 1
                b = 2
                c = 3
                d = 4
                e = 5
                f = 6
                return self.sudo().name, a, b, c, d, e, f
        """
    assert _lines(tmp_path, src) == [10]


def test_a_trailing_comment_above_counts_only_when_it_names_sudo(tmp_path: Path):
    named = """\
        class M:
            def f(self):
                self.check_access("read")  # before sudo(): the caller's own rights
                return self.sudo().name
        """
    other = """\
        class M:
            def f(self):
                total = len(self)  # count them
                return self.sudo().name, total
        """
    assert _lines(tmp_path, named) == []
    assert _lines(tmp_path, other) == [4]


def test_a_docstring_naming_sudo_justifies_the_whole_function(tmp_path: Path):
    src = '''\
        class M:
            def f(self):
                """Read as sudo: operators cannot see other teams' rules."""
                return self.sudo().name, self.env["x"].sudo().search([])

            def g(self):
                """Return the name."""
                return self.sudo().name
        '''
    assert _lines(tmp_path, src) == [8]


def test_sudo_on_an_environment_that_is_already_sudo_is_not_an_elevation(tmp_path):
    src = """\
        class M:
            def f(self):
                self = self.sudo()
                first = self.env["x"].sudo().search([], limit=1)
                return first | self.sudo().browse(self.ids)
        """
    assert _lines(tmp_path, src) == [3]


def test_sudo_after_a_conditional_or_foreign_rebinding_is_still_reported(tmp_path):
    src = """\
        class M:
            def f(self, other):
                if other:
                    self = self.sudo()
                return self.sudo().name

            def g(self):
                self = self.sudo()
                return self.env["x"].with_user(2).sudo().name, other.sudo().name
        """
    assert _lines(tmp_path, src) == [4, 5, 8, 9, 9]


def test_a_note_naming_sudo_in_the_function_above_does_not_carry_over(tmp_path):
    src = """\
        class M:
            def f(self):
                # sudo: the portal user cannot read it
                return self.sudo().name

            def g(self):
                return self.sudo().name
        """
    assert _lines(tmp_path, src) == [7]


def test_a_sudo_with_an_argument_does_not_elevate_the_rest_of_the_function(tmp_path):
    src = """\
        class M:
            def f(self, user):
                self = self.sudo(False)
                return self.env["x"].sudo().search([])

            def g(self, user):
                self = self.sudo(user)
                return self.env["x"].sudo().search([])
        """
    # 3 is `.sudo(False)` (drops rights); 7 and 8 are both reported
    assert _lines(tmp_path, src) == [4, 7, 8]


def test_rebinding_self_ends_the_elevation(tmp_path: Path):
    src = """\
        class M:
            def f(self):
                self = self.sudo()
                a = self.env["x"].sudo().search([])
                self = self.with_user(5)
                return a, self.env["x"].sudo().search([])
        """
    assert _lines(tmp_path, src) == [3, 6]
