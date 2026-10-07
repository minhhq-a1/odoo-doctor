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


def _lines(tmp_path: Path, src: str) -> list[int]:
    return [d.line for d in check_eval_usage(_write(tmp_path, src), "m", "17.0")]


def test_eval_imported_as_safe_eval_is_not_the_builtin(tmp_path: Path):
    """Odoo 8/9 era idiom, still found in ported addons: `safe_eval as eval`."""
    src = """\
        from odoo.tools.safe_eval import safe_eval as eval


        def f(expr):
            return eval(expr)
        """
    assert _lines(tmp_path, src) == []


def test_eval_rebound_at_module_level_is_not_the_builtin(tmp_path: Path):
    src = """\
        from odoo.tools import safe_eval as _safe

        eval = _safe.safe_eval


        def f(expr):
            return eval(expr)
        """
    assert _lines(tmp_path, src) == []


def test_eval_import_inside_try_is_not_the_builtin(tmp_path: Path):
    src = """\
        try:
            from odoo.tools.safe_eval import safe_eval as eval
        except ImportError:  # pragma: no cover
            from openerp.tools.safe_eval import safe_eval as eval


        def f(expr):
            return eval(expr)
        """
    assert _lines(tmp_path, src) == []


def test_exec_imported_under_another_name_does_not_hide_eval(tmp_path: Path):
    src = """\
        from my_sandbox import run as exec


        def f(expr, code):
            exec(code)
            return eval(expr)
        """
    assert _lines(tmp_path, src) == [6]


def test_a_method_named_eval_does_not_shadow_the_builtin(tmp_path: Path):
    src = """\
        class A:
            def eval(self, expr):
                return 1

            def run(self, expr):
                return eval(expr)
        """
    assert _lines(tmp_path, src) == [6]


def test_message_shows_the_evaluated_expression(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        def f(self, name):
            a = eval(self.domain)
            b = eval(f"x{name}")
        """,
    )
    opaque, built = check_eval_usage(f, "m", "17.0")
    assert "self.domain" in opaque.message and "not provably constant" in opaque.message
    assert "x{name}" in built.message and "built from" in built.message
    assert "literal_eval" in opaque.help and "safe_eval" in opaque.help
