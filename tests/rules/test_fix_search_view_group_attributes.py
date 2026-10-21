"""fix_search_view_group_attributes: string and expand leave the search <group>."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.rules.upgrade_safety.fixers import fix_search_view_group_attributes
from odoo_doctor.rules.upgrade_safety.search_view_group_attributes import (
    check_search_view_group_attributes,
)

from ._fix import fix_files
from ._module import view


def _fix(tmp_path: Path, xml: str):
    return fix_files(
        tmp_path,
        {"v.xml": xml},
        check_search_view_group_attributes,
        fix_search_view_group_attributes,
    )


def test_string_and_expand_removed_from_search_groups_only(tmp_path: Path):
    xml = view(
        '<search><field name="n"/>\n'
        '<group expand="0" string="Group By">\n<filter name="f" string="F" context="{}"/>\n</group>\n'
        '<group string="kept"><field name="x"/></group></search>'
    )
    diags, texts, result = _fix(tmp_path, xml)
    assert len(diags) == 1 and result.skipped_count == 0
    # every <group> of a search view is a search group; the finding covers all of them
    assert texts["v.xml"] == xml.replace(' expand="0" string="Group By"', "").replace(
        ' string="kept"', ""
    )


def test_form_group_in_the_same_file_is_untouched(tmp_path: Path):
    xml = view('<search><group string="g"><filter name="f"/></group></search>') + "\n"
    xml = xml.replace("</odoo>", "") + view(
        '<form><group string="keep"><field name="a"/></group></form>', "w"
    ).replace("<odoo>", "")
    _, texts, _ = _fix(tmp_path, xml)
    assert '<group><filter name="f"/></group>' in texts["v.xml"]
    assert '<group string="keep">' in texts["v.xml"]


def test_multiline_tag_keeps_its_format(tmp_path: Path):
    xml = view(
        '<search>\n<group\n    expand="1"\n    string="By"\n    name="g">\n'
        '<filter name="f"/>\n</group>\n</search>'
    )
    _, texts, _ = _fix(tmp_path, xml)
    assert '<group\n    name="g">' in texts["v.xml"]


def test_two_groups_on_one_line_and_idempotent(tmp_path: Path):
    xml = view(
        '<search><group string="a"><filter name="f"/></group><group expand="1"><filter name="g"/></group></search>'
    )
    _, texts, _ = _fix(tmp_path, xml)
    assert texts["v.xml"] == xml.replace(' string="a"', "").replace(' expand="1"', "")
    again = tmp_path / "again"
    again.mkdir()
    diags, texts2, _ = _fix(again, texts["v.xml"])
    assert diags == [] and texts2["v.xml"] == texts["v.xml"]


def test_crlf_preserved(tmp_path: Path):
    xml = view('<search><group string="a"><filter name="f"/></group></search>').replace(
        "\n", "\r\n"
    )
    _, texts, _ = _fix(tmp_path, xml)
    assert texts["v.xml"] == xml.replace(' string="a"', "")
