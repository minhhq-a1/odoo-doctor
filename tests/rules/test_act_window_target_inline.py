"""act-window-target-inline: Odoo 19 removed the 'inline' action target."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.act_window_target_inline import (
    check_act_window_target_inline,
)

from ._module import module_ctx

ACTION = """<odoo><record id="a" model="ir.actions.act_window">
<field name="name">A</field>
<field name="target">{target}</field>
</record></odoo>"""


def _diags(tmp_path: Path, files: dict[str, str]):
    return check_act_window_target_inline(module_ctx(tmp_path, files, "19.0"))


def test_inline_target_is_flagged(tmp_path: Path):
    diags = _diags(tmp_path, {"a.xml": ACTION.format(target="inline")})
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "act-window-target-inline",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert d.line == 3 and "current" in d.help


@pytest.mark.parametrize("target", ["current", "new", "fullscreen", "main"])
def test_remaining_targets_are_fine(tmp_path: Path, target: str):
    assert _diags(tmp_path, {"a.xml": ACTION.format(target=target)}) == []


def test_other_models_may_use_the_word(tmp_path: Path):
    xml = ACTION.replace("ir.actions.act_window", "ir.actions.server").format(
        target="inline"
    )
    assert _diags(tmp_path, {"a.xml": xml}) == []


def test_python_action_dict(tmp_path: Path):
    py = (
        "def a(self):\n    return {'type': 'ir.actions.act_window', 'target': 'inline'}\n"
        "def b(self):\n    return {'target': 'inline'}\n"
        "def c(self):\n    return {'res_model': 'x', 'target': 'new'}\n"
    )
    diags = _diags(tmp_path, {"models/m.py": py})
    assert [d.line for d in diags] == [2]
