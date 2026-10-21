"""fix_chatter_div_removed: a plain div.oe_chatter becomes <chatter/>."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.fixer import FixerRegistry, compute_fixes
from odoo_doctor.rules.upgrade_safety.chatter_div_removed import (
    check_chatter_div_removed,
)
from odoo_doctor.rules.upgrade_safety.fixers import fix_chatter_div_removed
from odoo_doctor.rules.upgrade_safety.view_tree_removed import check_view_tree_removed

from ._fix import fix_files
from ._module import module_ctx, view


def _fix(tmp_path: Path, xml: str):
    return fix_files(
        tmp_path, {"v.xml": xml}, check_chatter_div_removed, fix_chatter_div_removed
    )


DIV = (
    '    <div class="oe_chatter">\n'
    '        <field name="message_follower_ids"/>\n'
    '        <field name="activity_ids"/>\n'
    '        <field name="message_ids" options="{\'x\': 1}"/>\n'
    "    </div>"
)


def test_div_block_becomes_chatter_in_place(tmp_path: Path):
    xml = view(f'<form><sheet><field name="n"/></sheet>\n{DIV}\n</form>')
    diags, texts, result = _fix(tmp_path, xml)
    assert len(diags) == 1 and result.skipped_count == 0
    assert texts["v.xml"] == xml.replace(DIV, "    <chatter/>")


def test_text_after_the_closing_div_is_kept(tmp_path: Path):
    xml = view(
        '<form><div class="oe_chatter"><field name="message_ids"/></div><field name="n"/></form>'
    )
    _, texts, _ = _fix(tmp_path, xml)
    assert '<form><chatter/><field name="n"/></form>' in texts["v.xml"]


def test_empty_self_closing_div_becomes_chatter(tmp_path: Path):
    xml = view(
        '<xpath expr="//sheet" position="after"><div class="oe_chatter"/></xpath>'
    )
    diags, texts, result = _fix(tmp_path, xml)
    assert len(diags) == 1 and result.skipped_count == 0
    assert texts["v.xml"] == xml.replace('<div class="oe_chatter"/>', "<chatter/>")


def test_custom_content_is_not_fixed(tmp_path: Path):
    xml = view('<form><div class="oe_chatter"><span>mine</span></div></form>')
    diags, texts, result = _fix(tmp_path, xml)
    assert [d.confidence for d in diags] == ["medium"]  # never reaches the fixer
    assert texts["v.xml"] == xml and result.changed_files == {}
    assert fix_chatter_div_removed(diags[0], xml) is None


def test_div_with_other_attribute_is_not_fixed(tmp_path: Path):
    xml = view(
        '<form><div class="oe_chatter" invisible="1"><field name="message_ids"/></div></form>'
    )
    diags, texts, result = _fix(tmp_path, xml)
    assert [d.confidence for d in diags] == ["medium"]
    assert texts["v.xml"] == xml and result.changed_files == {}
    assert fix_chatter_div_removed(diags[0], xml) is None


def test_idempotent_and_crlf(tmp_path: Path):
    xml = view(f"<form>\n{DIV}\n</form>").replace("\n", "\r\n")
    _, texts, _ = _fix(tmp_path, xml)
    assert texts["v.xml"] == xml.replace(DIV.replace("\n", "\r\n"), "    <chatter/>")
    again = tmp_path / "again"
    again.mkdir()
    diags, _, _ = _fix(again, texts["v.xml"])
    assert diags == []


def test_tree_below_and_chatter_above_in_one_record_both_fixed(tmp_path: Path):
    for tree_first in (True, False):
        root = tmp_path / str(tree_first)
        root.mkdir()
        parts = [
            "<tree><field name='a'/></tree>",
            '<div class="oe_chatter"><field name="message_ids"/></div>',
        ]
        arch = (
            "<form>\n" + "\n".join(parts if tree_first else parts[::-1]) + "\n</form>"
        )
        ctx = module_ctx(root, {"v.xml": view(arch)})
        diags = check_chatter_div_removed(ctx) + check_view_tree_removed(ctx)
        reg = FixerRegistry()
        from odoo_doctor.rules.upgrade_safety.fixers import fix_view_tree_removed

        reg.register("chatter-div-removed", fix_chatter_div_removed, migration=True)
        reg.register("view-tree-removed", fix_view_tree_removed, migration=True)
        result, _ = compute_fixes(
            diags, {d.rule for d in diags}, reg, include_migration=True
        )
        (new,) = result.changed_files.values()
        assert "<chatter/>" in new and "<list>" in new
        assert "oe_chatter" not in new and "tree" not in new
        assert result.skipped_count == 0
