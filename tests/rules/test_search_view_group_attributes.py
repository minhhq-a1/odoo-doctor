"""search-view-group-attributes: Odoo 19 drops string / expand on a search <group>."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.upgrade_safety.search_view_group_attributes import (
    check_search_view_group_attributes,
)

from ._module import module_ctx, view


def _diags(tmp_path: Path, xml: str, version="19.0"):
    return check_search_view_group_attributes(
        module_ctx(tmp_path, {"v.xml": xml}, version)
    )


SEARCH = (
    '<search><field name="name"/>'
    '<group expand="0" string="Group By">'
    '<filter name="u" string="User" context="{\'group_by\': \'user_id\'}"/>'
    "</group></search>"
)


def test_group_with_string_and_expand_in_a_search_view(tmp_path: Path):
    diags = _diags(tmp_path, view(SEARCH, "s"))
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "search-view-group-attributes",
        "P1",
        "Upgrade Safety",
        "high",
    )
    assert "expand/string" in d.title
    assert d.line == 5


def test_bare_group_is_clean(tmp_path: Path):
    arch = "<search><group><filter name='u' string='U'/></group></search>"
    assert _diags(tmp_path, view(arch)) == []


def test_form_view_groups_are_not_touched(tmp_path: Path):
    arch = '<form><group string="Details" expand="0"><field name="a"/></group></form>'
    assert _diags(tmp_path, view(arch)) == []


def test_inherited_search_view_is_found_through_its_filters(tmp_path: Path):
    arch = (
        '<xpath expr="//search" position="inside">'
        '<group expand="0" string="More"><filter name="f" string="F"/></group></xpath>'
    )
    assert len(_diags(tmp_path, view(arch))) == 1


def test_inherited_form_group_without_filters_is_not_reported(tmp_path: Path):
    arch = '<xpath expr="//sheet" position="inside"><group string="More"><field name="a"/></group></xpath>'
    assert _diags(tmp_path, view(arch)) == []


def test_odoo_18_still_accepts_the_attributes(tmp_path: Path):
    from odoo_doctor.rules.registry import default_registry

    meta = next(
        m
        for m, _ in default_registry.get_rules()
        if m.name == "search-view-group-attributes"
    )
    assert meta.min_version == "19.0"
