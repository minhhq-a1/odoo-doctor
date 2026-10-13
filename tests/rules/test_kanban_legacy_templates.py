"""kanban-legacy-templates: Odoo 19 reads only the card / menu templates."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.upgrade_safety.kanban_legacy_templates import (
    check_kanban_legacy_templates,
)

from ._module import module_ctx, view


def _diags(tmp_path: Path, xml: str):
    return check_kanban_legacy_templates(module_ctx(tmp_path, {"v.xml": xml}, "19.0"))


def kanban(template: str) -> str:
    return (
        f'<kanban><templates><t t-name="{template}"><div><field name="name"/></div>'
        "</t></templates></kanban>"
    )


def test_kanban_box_is_flagged(tmp_path: Path):
    diags = _diags(tmp_path, view(kanban("kanban-box"), "k"))
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "kanban-legacy-templates",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert "kanban-box" in d.title and "card" in d.message and d.line == 5


def test_kanban_menu_is_flagged(tmp_path: Path):
    assert len(_diags(tmp_path, view(kanban("kanban-menu")))) == 1


@pytest.mark.parametrize("name", ["card", "menu"])
def test_new_names_are_clean(tmp_path: Path, name: str):
    assert _diags(tmp_path, view(kanban(name))) == []


def test_xpath_on_the_old_template(tmp_path: Path):
    arch = "<xpath expr=\"//t[@t-name='kanban-box']//field[@name='name']\" position='after'/>"
    assert len(_diags(tmp_path, view(arch))) == 1


def test_qweb_templates_are_skipped(tmp_path: Path):
    xml = view(kanban("kanban-box"), extra='<field name="type">qweb</field>\n')
    assert _diags(tmp_path, xml) == []


def test_gated_on_odoo_19(tmp_path: Path):
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m
        for m, _ in default_registry.get_rules()
        if m.name == "kanban-legacy-templates"
    )
    assert meta.min_version == "19.0"
