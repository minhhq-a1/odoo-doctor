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


def _diag(path, line=1, rule="r", confidence="high"):
    from odoo_doctor.core.diagnostics import Diagnostic

    return Diagnostic(
        module="m", file_path=str(path), line=line, column=0, rule=rule,
        category="Maintainability", severity="warning", tier="P3",
        source="native", confidence=confidence, title="t", message="m", help="h",
        odoo_version="17.0",
    )  # fmt: skip


def test_fix_keeps_crlf_and_bom(tmp_path):
    from odoo_doctor.core.fixer import compute_fixes

    path = tmp_path / "a.xml"
    path.write_bytes("﻿<a>\r\n<b/>\r\n</a>\r\n".encode())
    reg = FixerRegistry()
    reg.register("r", lambda d, text: text.replace("<b/>", "<c/>"))

    result, _ = compute_fixes([_diag(path)], {"r"}, reg)

    assert result.changed_files[str(path)] == "﻿<a>\r\n<c/>\r\n</a>\r\n"


def test_undecodable_file_is_skipped_not_a_crash(tmp_path):
    from odoo_doctor.core.fixer import compute_fixes

    path = tmp_path / "a.xml"
    path.write_bytes("<a>caf\xe9</a>".encode("latin-1"))
    reg = FixerRegistry()
    reg.register("r", lambda d, text: text + " ")

    result, _ = compute_fixes([_diag(path)], {"r"}, reg)

    assert result.changed_files == {}
    assert result.skipped_count == 1
    assert result.skipped_diags == [_diag(path)]


def test_migration_fixer_needs_opt_in(tmp_path):
    from odoo_doctor.core.fixer import compute_fixes

    path = tmp_path / "a.txt"
    path.write_text("a")
    reg = FixerRegistry()
    reg.register("r", lambda d, text: text + "!", migration=True)

    off, _ = compute_fixes([_diag(path)], {"r"}, reg)
    on, _ = compute_fixes([_diag(path)], {"r"}, reg, include_migration=True)

    assert off.changed_files == {}
    assert on.changed_files == {str(path): "a!"}


def test_applies_predicate_filters_per_finding():
    reg = FixerRegistry()
    reg.register("r", lambda d, text: text, applies=lambda d: d.line == 1)

    assert reg.can_fix(_diag("x", line=1), include_migration=False)
    assert not reg.can_fix(_diag("x", line=2), include_migration=False)
    assert not reg.can_fix(_diag("x", confidence="medium"), include_migration=False)
    assert not reg.can_fix(_diag("x", rule="other"), include_migration=False)


def test_migration_flag_in_can_fix():
    reg = FixerRegistry()
    reg.register("r", lambda d, text: text, migration=True)

    assert not reg.can_fix(_diag("x"), include_migration=False)
    assert reg.can_fix(_diag("x"), include_migration=True)
    assert reg.is_migration("r")


def test_diagnostics_are_applied_bottom_up(tmp_path):
    from odoo_doctor.core.fixer import compute_fixes

    path = tmp_path / "a.txt"
    path.write_text("one\ntwo\nthree\n")
    reg = FixerRegistry()

    def fixer(d, text):
        lines = text.splitlines(keepends=True)
        if lines[d.line - 1].strip() != d.title:  # the line must still be the target
            return None
        lines[d.line - 1 : d.line] = [f"{d.title}-a\n", f"{d.title}-b\n"]  # adds a line
        return "".join(lines)

    reg.register("r", fixer)
    diags = [_diag(path, 1), _diag(path, 3)]
    diags = [
        d.__class__(**{**d.__dict__, "title": t})
        for d, t in zip(diags, ["one", "three"])
    ]

    result, _ = compute_fixes(diags, {"r"}, reg)

    assert result.changed_files[str(path)] == "one-a\none-b\ntwo\nthree-a\nthree-b\n"
    assert result.skipped_count == 0


def test_result_that_does_not_parse_is_dropped(tmp_path):
    from odoo_doctor.core.fixer import compute_fixes

    path = tmp_path / "a.xml"
    path.write_text("<a/>")
    reg = FixerRegistry()
    reg.register("r", lambda d, text: "<a>")

    result, _ = compute_fixes([_diag(path)], {"r"}, reg)

    assert result.changed_files == {}
    assert result.skipped_diags == [_diag(path)]


def test_validate_text():
    from odoo_doctor.core.fixer import validate_text

    assert validate_text("a.xml", '<?xml version="1.0" encoding="utf-8"?><a/>')
    assert not validate_text("a.xml", "<a>")
    assert validate_text("a.py", "x = 1\n")
    assert not validate_text("a.py", "x = (\n")
    assert validate_text("a.csv", "anything (")


def test_write_fixed_is_byte_exact_and_keeps_mode(tmp_path):
    import os

    from odoo_doctor.core.fixer import write_fixed

    path = tmp_path / "a.xml"
    path.write_bytes(b"old")
    os.chmod(path, 0o640)

    write_fixed(path, "﻿<a>\r\n</a>\r\n")

    assert path.read_bytes() == "﻿<a>\r\n</a>\r\n".encode()
    assert (path.stat().st_mode & 0o777) == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["a.xml"]
