# src/odoo_doctor/reporters/html_report.py
"""Static HTML report: one self-contained file, no server and no network.

The page embeds the exact ``scan --json`` payload plus a small envelope (meta, rule
URLs, history). Everything in it comes from the scanned repository and is untrusted:
the JSON is escaped for a ``<script>`` element, the page script only uses
``textContent``, and a CSP meta pins the one inline script and style by hash.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from importlib import resources
from typing import NamedTuple

from odoo_doctor.rules.rule_docs import DOCS_BASE_URL, rule_doc_url

MAX_HTML_BYTES = 10 * 1024 * 1024
MAX_TREND_POINTS = 200
REPO_URL = "https://github.com/minhhq-a1/odoo-doctor"

_BS = chr(92)  # backslash, kept out of source literals on purpose
_JSON_ESCAPES = {
    "<": _BS + "u003c",
    ">": _BS + "u003e",
    "&": _BS + "u0026",
    chr(0x2028): _BS + "u2028",
    chr(0x2029): _BS + "u2029",
}
_PLACEHOLDER = re.compile(r"__(CSP|STYLE|DATA|SCRIPT)__")


class HtmlAssetsError(RuntimeError):
    """A packaged report asset (template, CSS or JS) could not be read."""


class HtmlReport(NamedTuple):
    html: str
    size: int  # UTF-8 bytes of the complete file
    truncated: dict  # low_findings / findings_total / findings_embedded
    over_limit: bool  # still above the threshold after dropping low findings


def embed_json(obj: object) -> str:
    """JSON text that is safe inside ``<script type="application/json">``.

    The text can neither close the element nor open an HTML comment, whatever the
    values hold. Parsing it gives back the original object.
    """
    text = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    for raw, escaped in _JSON_ESCAPES.items():
        text = text.replace(raw, escaped)
    return text


def _asset(name: str) -> str:
    try:
        folder = resources.files("odoo_doctor.reporters.html")
        return folder.joinpath(name).read_text(encoding="utf-8")
    except (OSError, ValueError, ModuleNotFoundError) as exc:
        raise HtmlAssetsError(f"cannot read report asset {name}: {exc}") from exc


def _csp_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def _count_findings(payload: dict) -> int:
    return sum(
        len(m.get("diagnostics", [])) for m in payload.get("modules", {}).values()
    )


def _without_low(payload: dict) -> dict:
    """A copy whose per-module diagnostics hold no ``low`` finding; input untouched."""
    slim = dict(payload)
    slim["modules"] = {
        name: {
            **module,
            "diagnostics": [
                d for d in module.get("diagnostics", []) if d.get("confidence") != "low"
            ],
        }
        for name, module in payload.get("modules", {}).items()
    }
    return slim


def _rule_urls(payload: dict) -> dict[str, str]:
    urls: dict[str, str] = {}
    for module in payload.get("modules", {}).values():
        for d in module.get("diagnostics", []):
            rule = d["rule"]
            if rule in urls:
                continue
            url = d.get("url") or rule_doc_url(rule)
            if url:
                urls[rule] = url
    return urls


def _finite(value: object) -> bool:
    """JSON would embed inf/nan as bare tokens, which ``JSON.parse`` rejects."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float, e.g. 10**309
        return False


def _modules_of(record: dict) -> dict:
    modules = record.get("modules")
    return modules if isinstance(modules, dict) else {}


def _trend(
    history: list[dict] | None, schema_version: object
) -> tuple[list[dict] | None, int]:
    """Records of the current score schema (newest ``MAX_TREND_POINTS``) + how many were dropped."""
    if history is None:
        return None, 0
    same = [r for r in history if r.get("score_schema_version") == schema_version]
    usable = [r for r in same if _finite((r.get("project") or {}).get("overall"))]
    points = [
        {
            "timestamp": r.get("timestamp"),
            "branch": r.get("branch"),
            "commit": r.get("commit"),
            "project": r["project"]["overall"],
            "modules": {
                name: m["overall"]
                for name, m in _modules_of(r).items()
                if isinstance(m, dict) and _finite(m.get("overall"))
            },
        }
        for r in usable[-MAX_TREND_POINTS:]
    ]
    return points, len(history) - len(same)


def _assemble(envelope: dict) -> str:
    style = _asset("report.css")
    script = _asset("report.js")
    csp = (
        "default-src 'none'; "
        f"script-src '{_csp_hash(script)}'; "
        f"style-src '{_csp_hash(style)}'; "
        "img-src data:; base-uri 'none'; form-action 'none'"
    )
    parts = {"CSP": csp, "STYLE": style, "DATA": embed_json(envelope), "SCRIPT": script}
    # One pass: text inserted for a placeholder is never scanned for placeholders.
    return _PLACEHOLDER.sub(lambda m: parts[m.group(1)], _asset("template.html"))


def render_html_report(
    payload: dict,
    *,
    meta: dict,
    history: list[dict] | None = None,
    history_skipped: int = 0,
    max_bytes: int = MAX_HTML_BYTES,
) -> HtmlReport:
    """Render the report. ``payload`` is the dict from ``build_payload()``."""
    total = _count_findings(payload)
    truncated = {"low_findings": 0, "findings_total": total, "findings_embedded": total}
    trend, dropped_schema = _trend(history, payload.get("score_schema_version"))
    rule_urls = _rule_urls(payload)

    def build(report: dict) -> str:
        return _assemble(
            {
                "report": report,
                "meta": meta,
                "rule_urls": rule_urls,
                "links": {"repo": REPO_URL, "rules": DOCS_BASE_URL},
                "history": trend,
                "history_skipped": history_skipped,
                "history_dropped_schema": dropped_schema,
                "truncated": truncated,
            }
        )

    html = build(payload)
    size = len(html.encode("utf-8"))
    if size > max_bytes:
        slim = _without_low(payload)
        embedded = _count_findings(slim)
        if embedded < total:  # there was something to drop
            truncated = {
                "low_findings": total - embedded,
                "findings_total": total,
                "findings_embedded": embedded,
            }
            html = build(slim)
            size = len(html.encode("utf-8"))
    return HtmlReport(html, size, truncated, size > max_bytes)
