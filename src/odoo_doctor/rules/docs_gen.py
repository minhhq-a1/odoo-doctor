# src/odoo_doctor/rules/docs_gen.py
"""Render rule documentation from RuleMeta + the rule_docs catalog.

Every output (``rules explain``, ``docs/rules.md``, the HTML page) is produced
here so the content cannot drift between surfaces.
"""

from __future__ import annotations

import html

from odoo_doctor.core.diagnostics import CATEGORIES
from odoo_doctor.rules.registry import RuleMeta, default_registry
from odoo_doctor.rules.rule_docs import RULE_DOCS, RuleDoc, rule_doc_url

_TIER_TEXT = {
    "P0": "P0 (critical)",
    "P1": "P1 (serious)",
    "P2": "P2 (moderate)",
    "P3": "P3 (advisory)",
}

_HEADER = (
    "<!-- GENERATED FILE: do not edit by hand. Source: "
    "src/odoo_doctor/rules/rule_docs.py. Regenerate with "
    "`odoo-doctor rules docs --out docs/rules.md`. -->"
)


def _rules_by_category() -> list[tuple[str, list[RuleMeta]]]:
    grouped: dict[str, list[RuleMeta]] = {}
    for meta, _ in default_registry.get_rules():
        grouped.setdefault(meta.category, []).append(meta)
    ordered = [c for c in CATEGORIES if c in grouped]
    ordered += sorted(c for c in grouped if c not in CATEGORIES)
    return [(c, sorted(grouped[c], key=lambda m: (m.tier, m.name))) for c in ordered]


def _meta_fields(meta: RuleMeta) -> list[tuple[str, str]]:
    fields = [
        ("Category", meta.category),
        ("Tier", _TIER_TEXT.get(meta.tier, meta.tier)),
        ("Severity", meta.severity),
        ("Confidence", meta.default_confidence),
        ("Min Odoo version", meta.min_version or "any"),
        ("Needs module context", "yes" if meta.needs_context else "no"),
        ("Fixable", "yes" if meta.fixable else "no"),
    ]
    if meta.requires_capabilities:
        fields.append(("Requires", ", ".join(sorted(meta.requires_capabilities))))
    return fields


def _examples(doc: RuleDoc) -> list[tuple[str, str]]:
    out = []
    if doc.bad:
        out.append(("Bad", doc.bad))
    if doc.good:
        out.append(("Good", doc.good))
    return out


def render_rule_text(meta: RuleMeta) -> str:
    """Plain-text explanation used by ``odoo-doctor rules explain``."""
    lines = [f"Rule: {meta.name}"]
    lines += [f"{k}: {v}" for k, v in _meta_fields(meta)]
    doc = RULE_DOCS.get(meta.name)
    if doc is not None:
        lines += ["", f"Detects: {doc.detects}"]
        if doc.why:
            lines.append(f"Why: {doc.why}")
        if doc.fix:
            lines.append(f"Fix: {doc.fix}")
        if doc.notes:
            lines.append(f"Note: {doc.notes}")
        for label, code in _examples(doc):
            lines += ["", f"{label}:"]
            lines += [f"    {line}" for line in code.splitlines()]
    url = rule_doc_url(meta.name)
    if url:
        lines += ["", f"Docs: {url}"]
    return "\n".join(lines)


def render_markdown() -> str:
    """The full rules reference page (docs/rules.md)."""
    groups = _rules_by_category()
    total = sum(len(rules) for _, rules in groups)
    out = [
        _HEADER,
        "",
        "# Built-in Rules",
        "",
        f"Odoo Doctor ships {total} native rules. Each rule has a **tier** "
        "(P0 critical, P1 serious, P2 moderate, P3 advisory), a **category** and "
        "a **confidence**; only high-confidence findings affect the score.",
        "",
        "| Rule | Tier | Category | Severity | Confidence | Fixable |",
        "|------|------|----------|----------|------------|---------|",
    ]
    for category, rules in groups:
        for m in rules:
            out.append(
                f"| [{m.name}](#{m.name}) | {m.tier} | {category} | {m.severity} "
                f"| {m.default_confidence} | {'Yes' if m.fixable else ''} |"
            )
    for category, rules in groups:
        out += ["", f"## {category}"]
        for m in rules:
            doc = RULE_DOCS.get(m.name)
            out += ["", f"### {m.name}", ""]
            meta_line = " · ".join(
                f"**{k}**: {v}"
                for k, v in _meta_fields(m)
                if k in ("Tier", "Severity", "Confidence", "Min Odoo version")
            )
            if m.fixable:
                meta_line += " · **Fixable**: yes"
            out += [meta_line, ""]
            if doc is None:
                out.append("_No documentation yet._")
                continue
            out.append(f"**Detects**: {doc.detects}")
            if doc.why:
                out += ["", f"**Why**: {doc.why}"]
            if doc.fix:
                out += ["", f"**Fix**: {doc.fix}"]
            if doc.notes:
                out += ["", f"**Note**: {doc.notes}"]
            for label, code in _examples(doc):
                out += ["", f"{label}:", "", f"```{doc.lang}", code, "```"]
    return "\n".join(out) + "\n"


def render_html() -> str:
    """A dependency-free static page, publishable as-is (e.g. GitHub Pages)."""
    esc = html.escape
    groups = _rules_by_category()
    body = ["<h1>Odoo Doctor — Built-in Rules</h1>", "<nav><ul>"]
    for category, rules in groups:
        items = ", ".join(f'<a href="#{esc(m.name)}">{esc(m.name)}</a>' for m in rules)
        body.append(f"<li><strong>{esc(category)}</strong>: {items}</li>")
    body.append("</ul></nav>")
    for category, rules in groups:
        body.append(f"<h2>{esc(category)}</h2>")
        for m in rules:
            doc = RULE_DOCS.get(m.name)
            body.append(f'<section id="{esc(m.name)}"><h3>{esc(m.name)}</h3>')
            facts = " · ".join(
                f"<b>{esc(k)}</b>: {esc(v)}"
                for k, v in _meta_fields(m)
                if k in ("Tier", "Severity", "Confidence", "Min Odoo version")
            )
            body.append(f"<p>{facts}</p>")
            if doc is None:
                body.append("<p><em>No documentation yet.</em></p></section>")
                continue
            body.append(f"<p><b>Detects</b>: {esc(doc.detects)}</p>")
            if doc.why:
                body.append(f"<p><b>Why</b>: {esc(doc.why)}</p>")
            if doc.fix:
                body.append(f"<p><b>Fix</b>: {esc(doc.fix)}</p>")
            if doc.notes:
                body.append(f"<p><b>Note</b>: {esc(doc.notes)}</p>")
            for label, code in _examples(doc):
                body.append(f"<p>{label}:</p><pre><code>{esc(code)}</code></pre>")
            body.append("</section>")
    style = (
        "body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;"
        "padding:0 1rem}pre{background:#f4f4f4;padding:.75rem;overflow:auto}"
        "section{border-top:1px solid #ddd;margin-top:1.5rem}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Odoo Doctor rules</title><style>{style}</style></head><body>"
        + "\n".join(body)
        + "</body></html>\n"
    )
