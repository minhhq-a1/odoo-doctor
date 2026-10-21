"""Fixer registry maps rule names to fix functions."""

from __future__ import annotations

from odoo_doctor.core.fixer import FixerRegistry


def test_register_and_lookup():
    reg = FixerRegistry()

    def _fix(diag, text):
        return text + "\n# fixed"

    reg.register("some-rule", _fix)
    assert reg.get("some-rule") is _fix
    assert reg.get("missing") is None
    assert "some-rule" in reg


def test_fixer_returns_none_when_unfixable():
    reg = FixerRegistry()
    reg.register("r", lambda diag, text: None)
    assert reg.get("r")(object(), "abc") is None


def test_compute_fixes_skips_a_file_outside_the_allowed_roots(tmp_path):
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.fixer import compute_fixes

    inside = tmp_path / "repo"
    inside.mkdir()
    (inside / "a.txt").write_text("a")
    outside = tmp_path / "outside.txt"
    outside.write_text("o")
    reg = FixerRegistry()
    reg.register("r", lambda diag, text: text + "!")

    def diag(path):
        return Diagnostic(
            module="m", file_path=str(path), line=1, column=0, rule="r",
            category="Maintainability", severity="warning", tier="P3",
            source="native", confidence="high", title="t", message="m", help="h",
            odoo_version="17.0",
        )  # fmt: skip

    result, _ = compute_fixes(
        [diag(inside / "a.txt"), diag(outside)],
        {"r"},
        reg,
        allowed_roots=[inside],
    )
    assert set(result.changed_files) == {str(inside / "a.txt")}
    assert result.skipped_count == 1
