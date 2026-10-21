"""Text-level XML helpers used by the migration fixers."""

from __future__ import annotations

from lxml import etree

from odoo_doctor.rules.upgrade_safety._xml_text import (
    end_tag_for,
    line_of_offset,
    record_span,
    remove_attr,
    rename_attr_value,
    start_tags,
    tags_ending_on_line,
)

DOC = """<odoo>
  <!-- <record id="ghost"> -->
  <record id="a" model="ir.ui.view">
    <field name="arch" type="xml"><![CDATA[<record id="no">]]></field>
  </record>
  <record id="b" model="ir.ui.view">
    <field name="x"/>
  </record>
</odoo>
"""


def test_record_span_skips_comment_and_cdata():
    start, end = record_span(DOC, 4)
    assert DOC[start:end].startswith('<record id="a"')
    assert DOC[start:end].endswith("</record>")
    start, end = record_span(DOC, 7)
    assert DOC[start:end].startswith('<record id="b"')


def test_record_span_none_outside_a_record():
    assert record_span(DOC, 1) is None
    assert record_span(DOC, 2) is None


def test_start_tags_document_order_on_one_line():
    text = "<x><tree><tree/></tree></x>"
    found = start_tags(text, "tree")
    assert [(t.start, t.self_closing) for t in found] == [(3, False), (9, True)]


def test_end_tag_balanced_for_nested_same_name():
    text = "<tree><tree/><tree></tree></tree>!"
    outer = start_tags(text, "tree")[0]
    closing = end_tag_for(text, outer)
    assert text[closing.start : closing.end] == "</tree>"
    assert closing.end == len(text) - 1
    assert end_tag_for(text, start_tags(text, "tree")[1]) is None


def test_tags_ending_on_line_matches_lxml_sourceline():
    text = '<a>\n<b\n  x="1"\n  y="2">\n</b></a>'
    (tag,) = tags_ending_on_line(text, 4, "b")
    assert text[tag.start : tag.end] == '<b\n  x="1"\n  y="2">'
    assert etree.fromstring(text.encode()).find("b").sourceline == 4


def test_remove_attr_multiline_keeps_the_others():
    tag = '<group\n    string="By"\n    expand="1"\n    name="g">'
    assert remove_attr(tag, "expand") == '<group\n    string="By"\n    name="g">'
    assert remove_attr(tag, "string") == '<group\n    expand="1"\n    name="g">'


def test_remove_attr_last_attribute_leaves_no_space():
    assert remove_attr('<group string="x">', "string") == "<group>"
    assert remove_attr("<group string='x'/>", "string") == "<group/>"


def test_attr_lookalike_inside_a_value_is_ignored():
    tag = """<group expr="a string='x'" string="y">"""
    assert remove_attr(tag, "string") == """<group expr="a string='x'">"""


def test_rename_attr_value_either_quote_and_only_when_it_matches():
    assert rename_attr_value(
        '<field name="groups_id"/>', "name", "groups_id", "group_ids"
    ) == ('<field name="group_ids"/>')
    assert rename_attr_value(
        "<field name='groups_id'/>", "name", "groups_id", "group_ids"
    ) == ("<field name='group_ids'/>")
    other = '<field name="other"/>'
    assert rename_attr_value(other, "name", "groups_id", "group_ids") == other


def test_crlf_gives_the_same_offsets_and_lines():
    crlf = DOC.replace("\n", "\r\n")
    start, end = record_span(crlf, 7)
    assert crlf[start:end].startswith('<record id="b"')
    assert line_of_offset(crlf, start) == 6
