"""Score badge: valid SVG and shields.io endpoint JSON."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from odoo_doctor.reporters.badge import render_badge_endpoint, render_badge_svg


@pytest.mark.parametrize(
    "score,label,color,shields",
    [
        (95.0, "Excellent", "#2ea44f", "brightgreen"),
        (80.0, "Good", "#97ca00", "yellowgreen"),
        (60.0, "Needs work", "#dfb317", "yellow"),
        (10.0, "Critical", "#e05d44", "red"),
    ],
)
def test_svg_and_endpoint_by_label(score, label, color, shields):
    svg = render_badge_svg(score)
    root = ET.fromstring(svg)  # well-formed XML
    assert root.tag.endswith("svg")
    assert color in svg and f"{score:.1f} {label}" in svg
    assert root.attrib["role"] == "img"
    data = json.loads(render_badge_endpoint(score))
    assert data == {
        "schemaVersion": 1,
        "label": "odoo-doctor",
        "message": f"{score:.1f} {label}",
        "color": shields,
    }


def test_svg_escapes_custom_label():
    svg = render_badge_svg(90.0, label='a<b&"c')
    ET.fromstring(svg)
    assert "<b&" not in svg
