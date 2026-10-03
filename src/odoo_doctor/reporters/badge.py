# src/odoo_doctor/reporters/badge.py
"""Score badge: a self-contained SVG, or a shields.io endpoint JSON.

Both are generated locally so a README badge needs no running service: commit
the SVG, publish it from CI (gh-pages / release asset), or serve the JSON to
https://img.shields.io/endpoint?url=...
"""

from __future__ import annotations

import json
from html import escape

from odoo_doctor.core.scoring import score_label

LABEL = "odoo-doctor"

# label -> (hex colour for the SVG, shields.io named colour)
_COLORS = {
    "Excellent": ("#2ea44f", "brightgreen"),
    "Good": ("#97ca00", "yellowgreen"),
    "Needs work": ("#dfb317", "yellow"),
    "Critical": ("#e05d44", "red"),
}


def _message(overall: float) -> str:
    return f"{overall:.1f} {score_label(overall)}"


def _text_width(text: str) -> int:
    # Verdana 11px averages ~6.6px/char; padded estimate avoids a font dependency.
    return int(len(text) * 6.6) + 10


def render_badge_svg(overall: float, label: str = LABEL) -> str:
    message = _message(overall)
    color = _COLORS[score_label(overall)][0]
    lw, mw = _text_width(label), _text_width(message)
    total = lw + mw
    title = escape(f"{label}: {message}")
    label_x, msg_x = lw * 5, (lw + mw / 2) * 10
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{title}"><title>{title}</title>'
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/>'
        "</clipPath>"
        f'<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/>'
        f'<rect x="{lw}" width="{mw}" height="20" fill="{color}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="110" '
        'text-rendering="geometricPrecision">'
        f'<text x="{label_x:.0f}" y="140" transform="scale(.1)" '
        f'textLength="{(lw - 10) * 10}">{escape(label)}</text>'
        f'<text x="{msg_x:.0f}" y="140" transform="scale(.1)" '
        f'textLength="{(mw - 10) * 10}">{escape(message)}</text></g></svg>\n'
    )


def render_badge_endpoint(overall: float, label: str = LABEL) -> str:
    """shields.io 'endpoint' schema (schemaVersion 1)."""
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "label": label,
                "message": _message(overall),
                "color": _COLORS[score_label(overall)][1],
            },
            indent=2,
        )
        + "\n"
    )
