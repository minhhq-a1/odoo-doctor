"""chatter-div-removed: Odoo 18 compiles only the <chatter/> tag."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.upgrade_safety.chatter_div_removed import (
    check_chatter_div_removed,
)

from ._module import module_ctx, view


def _diags(tmp_path: Path, xml: str, version="19.0"):
    return check_chatter_div_removed(module_ctx(tmp_path, {"v.xml": xml}, version))


FORM = (
    '<form><sheet><field name="name"/></sheet>'
    '<div class="oe_chatter"><field name="message_follower_ids"/>'
    '<field name="message_ids"/></div></form>'
)


def test_oe_chatter_div_is_flagged(tmp_path: Path):
    diags = _diags(tmp_path, view(FORM, "f"))
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence, d.severity) == (
        "chatter-div-removed",
        "P1",
        "Upgrade Safety",
        "high",
        "warning",
    )
    assert "<chatter/>" in d.help and d.line == 5


def test_chatter_tag_is_clean(tmp_path: Path):
    assert _diags(tmp_path, view("<form><sheet/><chatter/></form>")) == []


def test_extra_classes_and_groups_attribute(tmp_path: Path):
    arch = (
        '<xpath expr="//sheet" position="after">'
        '<div class="oe_chatter o_x" groups="base.group_user"/></xpath>'
    )
    assert len(_diags(tmp_path, view(arch))) == 1


def test_similar_class_names_are_not_matched(tmp_path: Path):
    arch = '<form><div class="o_portal_chatter oe_chatter_box"/></form>'
    assert _diags(tmp_path, view(arch)) == []


def test_available_from_odoo_18(tmp_path: Path):
    assert len(_diags(tmp_path, view(FORM), "18.0")) == 1
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m for m, _ in default_registry.get_rules() if m.name == "chatter-div-removed"
    )
    assert meta.min_version == "18.0"
