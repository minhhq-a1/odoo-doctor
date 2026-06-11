"""sudo-without-comment flags .sudo() calls lacking a justifying comment."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

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
