"""unsafe-template-render flags QWeb t-raw output that is not HTML-escaped."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.unsafe_template_render import (
    check_unsafe_template_render,
)


def _manifest(files: list[str]) -> str:
    joined = ", ".join(f'"{f}"' for f in files)
    return '{"name": "M", "depends": [], "data": [%s], "license": "LGPL-3"}' % joined


def _ctx(tmp_path: Path, xml: str) -> object:
    mod = tmp_path / "m"
    (mod / "views").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(_manifest(["views/t.xml"]))
    (mod / "views" / "t.xml").write_text(xml)
    return build_project_graph([tmp_path], odoo_version="17.0").modules["m"]


def test_t_raw_is_flagged(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        """<odoo>
  <template id="report_body">
    <div t-raw="doc.user_comment"/>
  </template>
</odoo>""",
    )
    diags = check_unsafe_template_render(ctx)
    assert any(d.rule == "unsafe-template-render" for d in diags)
    d = next(d for d in diags if d.rule == "unsafe-template-render")
    assert d.category == "Security"
    assert d.confidence == "medium"
    assert d.line == 3


def test_t_raw_zero_body_idiom_is_not_flagged(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        """<odoo>
  <template id="layout">
    <div class="wrap"><t t-raw="0"/></div>
  </template>
</odoo>""",
    )
    diags = check_unsafe_template_render(ctx)
    assert not any(d.rule == "unsafe-template-render" for d in diags)


def test_t_esc_is_not_flagged(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        """<odoo>
  <template id="safe">
    <span t-esc="doc.name"/>
    <span t-out="doc.name"/>
  </template>
</odoo>""",
    )
    diags = check_unsafe_template_render(ctx)
    assert not any(d.rule == "unsafe-template-render" for d in diags)


def test_xml_comment_does_not_crash(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        """<odoo>
  <!-- a comment node -->
  <template id="ok"><span t-esc="x"/></template>
</odoo>""",
    )
    # Must not raise on comment/PI nodes and must produce no findings.
    assert check_unsafe_template_render(ctx) == []
