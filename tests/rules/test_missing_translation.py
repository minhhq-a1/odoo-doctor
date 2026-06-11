"""missing-translation flags untranslated user-facing exception messages."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.correctness.missing_translation import (
    check_missing_translation,
)


def _write(tmp_path: Path, src: str) -> Path:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return f


def test_bare_string_in_user_error_is_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from odoo.exceptions import UserError

        def f():
            raise UserError("Something went wrong")
        """,
    )
    diags = check_missing_translation(f, "m", "17.0")
    assert any(d.rule == "missing-translation" for d in diags)


def test_translated_string_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from odoo import _
        from odoo.exceptions import UserError

        def f():
            raise UserError(_("Something went wrong"))
        """,
    )
    diags = check_missing_translation(f, "m", "17.0")
    assert not any(d.rule == "missing-translation" for d in diags)


def test_non_user_facing_exception_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        def f():
            raise ValueError("internal")
        """,
    )
    diags = check_missing_translation(f, "m", "17.0")
    assert not any(d.rule == "missing-translation" for d in diags)
