"""eval-usage flags eval/exec calls on non-literal input."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.security.eval_usage import check_eval_usage


def _write(tmp_path: Path, src: str) -> Path:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return f


def test_eval_on_variable_is_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        def f(expr):
            return eval(expr)
        """,
    )
    diags = check_eval_usage(f, "m", "17.0")
    assert any(d.rule == "eval-usage" for d in diags)


def test_exec_is_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        def f(code):
            exec(code)
        """,
    )
    diags = check_eval_usage(f, "m", "17.0")
    assert any(d.rule == "eval-usage" for d in diags)


def test_safe_eval_import_is_not_builtin_eval(tmp_path: Path):
    # odoo's safe_eval is a different name; we only flag builtin eval/exec.
    f = _write(
        tmp_path,
        """\
        from odoo.tools import safe_eval

        def f(expr):
            return safe_eval(expr)
        """,
    )
    diags = check_eval_usage(f, "m", "17.0")
    assert not any(d.rule == "eval-usage" for d in diags)
