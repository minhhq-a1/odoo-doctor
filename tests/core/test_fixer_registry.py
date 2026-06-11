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
