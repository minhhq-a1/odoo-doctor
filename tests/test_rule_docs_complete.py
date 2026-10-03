"""Rule docs: every rule is documented and docs/rules.md is generated, not hand-edited."""

from __future__ import annotations

from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (registers all built-in rules)
from odoo_doctor.rules.docs_gen import render_html, render_markdown
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.rule_docs import DOCS_BASE_URL, RULE_DOCS, rule_doc_url

DOCS = Path(__file__).resolve().parents[1] / "docs" / "rules.md"


def test_all_rules_have_catalog_entry():
    registered = {meta.name for meta, _ in default_registry.get_rules()}
    assert registered - set(RULE_DOCS) == set(), "rules missing from rule_docs.py"
    assert set(RULE_DOCS) - registered == set(), "stale entries in rule_docs.py"


def test_catalog_entries_are_complete():
    for name, doc in RULE_DOCS.items():
        assert doc.detects.strip(), f"{name}: empty 'detects'"
        assert doc.fix.strip(), f"{name}: empty 'fix'"


def test_docs_page_is_up_to_date():
    assert DOCS.read_text(encoding="utf-8") == render_markdown(), (
        "docs/rules.md is stale. Run: odoo-doctor rules docs --out docs/rules.md"
    )


def test_every_rule_has_anchor_heading():
    text = render_markdown()
    for meta, _ in default_registry.get_rules():
        assert f"\n### {meta.name}\n" in text


def test_deep_link_format():
    assert rule_doc_url("eval-usage") == f"{DOCS_BASE_URL}#eval-usage"
    assert rule_doc_url("E501") is None


def test_html_page_contains_every_rule():
    page = render_html()
    for meta, _ in default_registry.get_rules():
        assert f'id="{meta.name}"' in page
