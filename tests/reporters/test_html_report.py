"""Static HTML report: envelope, escaping, size cut, CSP and template assembly."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from html.parser import HTMLParser
from importlib import resources

import pytest

import odoo_doctor.reporters.html_report as html_report_module
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import SCORE_SCHEMA_VERSION, score_diagnostics
from odoo_doctor.reporters.html_report import (
    MAX_HTML_BYTES,
    HtmlAssetsError,
    embed_json,
    render_html_report,
)
from odoo_doctor.reporters.json_report import build_payload, render_json

BS = chr(92)  # a backslash, so this file holds no raw escape sequences
EVIL = "</script><img src=x onerror=alert(1)>"
LS = chr(0x2028)

META = {
    "project": "demo",
    "tool_version": "0.0.0",
    "generated_at": "2026-10-15T09:00:00+00:00",
    "scope": {"partial": False, "diff": None, "modules": []},
    "baseline": None,
    "commit": "abc1234",
    "branch": "main",
}


def make_diag(**overrides) -> Diagnostic:
    base = {
        "module": "m",
        "file_path": "m/models/a.py",
        "line": 3,
        "column": 0,
        "rule": "eval-usage",
        "category": "Security",
        "severity": "warning",
        "tier": "P1",
        "source": "native",
        "confidence": "high",
        "title": "title",
        "message": "message",
        "help": "help",
        "odoo_version": "17.0",
    }
    base.update(overrides)
    return Diagnostic(**base)


def make_payload(diags: list[Diagnostic]) -> dict:
    modules = sorted({d.module for d in diags}) or ["m"]
    scores = {
        name: score_diagnostics(
            [d for d in diags if d.module == name],
            [True] * len([d for d in diags if d.module == name]),
        )
        for name in modules
    }
    return build_payload(diags, scores)


def envelope_of(html: str) -> dict:
    m = re.search(
        r'<script type="application/json" id="od-data">(.*?)</script>', html, re.DOTALL
    )
    assert m, "data block missing"
    return json.loads(m.group(1))


def history_record(overall: float, *, schema=SCORE_SCHEMA_VERSION, branch="main"):
    return {
        "history_schema_version": 1,
        "score_schema_version": schema,
        "tool_version": "0.9.3",
        "timestamp": f"2026-10-1{int(overall % 9)}T00:00:00+00:00",
        "commit": "deadbeefcafe",
        "branch": branch,
        "project": {"overall": overall, "label": "Good", "module_count": 1},
        "modules": {"m": {"overall": overall, "label": "Good"}},
    }


# --- embed_json ------------------------------------------------------------


def test_embed_json_escapes_html_significant_characters():
    text = embed_json({"v": f"</script><!-- & > {LS}"})
    for ch in ("<", ">", "&", LS):
        assert ch not in text
    assert BS + "u003c" in text and BS + "u003e" in text and BS + "u0026" in text
    assert json.loads(text) == {"v": f"</script><!-- & > {LS}"}


def test_embed_json_round_trips_non_ascii_paths():
    value = {"p": "mô-đun/tệp.py"}
    assert json.loads(embed_json(value)) == value


# --- envelope --------------------------------------------------------------


def test_envelope_report_equals_the_json_payload_when_nothing_is_cut():
    diags = [
        make_diag(),
        make_diag(line=9, confidence="low", rule="sudo-without-comment"),
    ]
    payload = make_payload(diags)
    result = render_html_report(payload, meta=META)
    env = envelope_of(result.html)
    assert env["report"] == payload
    assert env["meta"] == META
    assert env["truncated"] == {
        "low_findings": 0,
        "findings_total": 2,
        "findings_embedded": 2,
    }
    assert env["history"] is None
    assert result.over_limit is False
    assert result.size == len(result.html.encode("utf-8"))


def test_envelope_payload_matches_render_json_text():
    diags = [make_diag()]
    scores = {"m": score_diagnostics(diags, [True])}
    env = envelope_of(render_html_report(build_payload(diags, scores), meta=META).html)
    assert env["report"] == json.loads(render_json(diags, scores))


def test_rule_urls_cover_rules_with_docs_and_prefer_the_diagnostic_url():
    diags = [
        make_diag(rule="eval-usage"),
        make_diag(rule="external-rule", url="https://example.com/r"),
        make_diag(rule="no-docs-anywhere"),
    ]
    env = envelope_of(render_html_report(make_payload(diags), meta=META).html)
    assert env["rule_urls"]["external-rule"] == "https://example.com/r"
    assert env["rule_urls"]["eval-usage"].endswith("#eval-usage")
    assert "no-docs-anywhere" not in env["rule_urls"]


def test_envelope_carries_https_links_for_the_footer():
    env = envelope_of(render_html_report(make_payload([make_diag()]), meta=META).html)
    assert env["links"]["repo"].startswith("https://")
    assert env["links"]["rules"].startswith("https://")


def test_unreadable_assets_raise_a_dedicated_error(monkeypatch):
    def boom(_package):
        raise ModuleNotFoundError("odoo_doctor.reporters.html")

    monkeypatch.setattr(html_report_module.resources, "files", boom)
    with pytest.raises(HtmlAssetsError):
        render_html_report(make_payload([make_diag()]), meta=META)


def test_undecodable_assets_raise_the_dedicated_error(monkeypatch):
    class _Folder:
        def joinpath(self, _name):
            return self

        def read_text(self, encoding="utf-8"):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(html_report_module.resources, "files", lambda _p: _Folder())
    with pytest.raises(HtmlAssetsError):
        render_html_report(make_payload([make_diag()]), meta=META)


# --- size cut --------------------------------------------------------------


def test_over_threshold_drops_low_findings_on_a_copy_only():
    diags = [make_diag(line=i) for i in range(1, 4)] + [
        make_diag(line=10 + i, confidence="low", message="x" * 400) for i in range(40)
    ]
    payload = make_payload(diags)
    before = json.dumps(payload, sort_keys=True)

    full = render_html_report(payload, meta=META)
    limit = full.size - 1000  # force the cut
    cut = render_html_report(payload, meta=META, max_bytes=limit)

    assert json.dumps(payload, sort_keys=True) == before  # input untouched
    env = envelope_of(cut.html)
    assert env["truncated"] == {
        "low_findings": 40,
        "findings_total": 43,
        "findings_embedded": 3,
    }
    assert cut.truncated == env["truncated"]
    embedded = env["report"]["modules"]["m"]["diagnostics"]
    assert len(embedded) == 3 and all(d["confidence"] != "low" for d in embedded)
    for key in payload:
        if key != "modules":
            assert env["report"][key] == payload[key]
    assert env["report"]["modules"]["m"]["score"] == payload["modules"]["m"]["score"]
    assert cut.size < full.size and cut.over_limit is False


def test_still_over_after_dropping_low_keeps_high_and_medium():
    diags = [make_diag(line=i, message="y" * 500) for i in range(1, 30)]
    payload = make_payload(diags)
    result = render_html_report(payload, meta=META, max_bytes=500)
    env = envelope_of(result.html)
    assert result.over_limit is True
    assert env["truncated"]["low_findings"] == 0
    assert len(env["report"]["modules"]["m"]["diagnostics"]) == 29


def test_default_threshold_is_ten_mebibytes():
    assert MAX_HTML_BYTES == 10 * 1024 * 1024


# --- history ---------------------------------------------------------------


def test_history_keeps_only_the_current_score_schema_and_trims():
    records = [
        history_record(80.0),
        history_record(70.0, schema=SCORE_SCHEMA_VERSION + 1),
        history_record(90.0, branch="feature/x"),
    ]
    env = envelope_of(
        render_html_report(
            make_payload([make_diag()]), meta=META, history=records, history_skipped=2
        ).html
    )
    assert [h["project"] for h in env["history"]] == [80.0, 90.0]
    assert env["history"][1]["branch"] == "feature/x"
    assert env["history"][0]["modules"] == {"m": 80.0}
    assert env["history_skipped"] == 2
    assert env["history_dropped_schema"] == 1


def test_a_history_record_whose_modules_is_not_a_dict_counts_as_empty():
    bad = history_record(75.0)
    bad["modules"] = ["m"]
    none = history_record(76.0)
    none["modules"] = None
    env = envelope_of(
        render_html_report(
            make_payload([make_diag()]), meta=META, history=[bad, none]
        ).html
    )
    assert [h["project"] for h in env["history"]] == [75.0, 76.0]
    assert [h["modules"] for h in env["history"]] == [{}, {}]


def test_history_is_capped_at_200_newest_records():
    records = [history_record(float(i % 100)) for i in range(250)]
    env = envelope_of(
        render_html_report(make_payload([make_diag()]), meta=META, history=records).html
    )
    assert len(env["history"]) == 200


def test_a_single_history_record_is_still_embedded():
    env = envelope_of(
        render_html_report(
            make_payload([make_diag()]), meta=META, history=[history_record(88.0)]
        ).html
    )
    assert len(env["history"]) == 1


# --- security and structure -----------------------------------------------


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_hostile_values_cannot_break_out_of_the_data_block():
    diags = [
        make_diag(
            module="m<b>",
            file_path='a"><svg onload=alert(1)>.py',
            message=EVIL,
            title=f"t{LS}t",
            help=EVIL,
        )
    ]
    meta = dict(META, branch=EVIL, project=EVIL)
    html = render_html_report(make_payload(diags), meta=meta).html

    assert "</script><img" not in html
    assert html.lower().count("<script") == 2  # data block + page script
    parser = _Collect()
    parser.feed(html)
    assert not [t for t, _ in parser.tags if t in {"img", "svg", "iframe"}]
    env = envelope_of(html)
    assert "m<b>" in env["report"]["modules"]
    d = env["report"]["modules"]["m<b>"]["diagnostics"][0]
    assert d["module"] == "m<b>"
    assert d["message"] == EVIL and d["file_path"] == 'a"><svg onload=alert(1)>.py'
    assert d["title"] == f"t{LS}t"
    assert env["meta"]["branch"] == EVIL


def test_placeholder_text_in_the_data_is_not_substituted_again():
    diags = [make_diag(message="__SCRIPT__ __STYLE__ __CSP__ __DATA__")]
    html = render_html_report(make_payload(diags), meta=META).html
    env = envelope_of(html)
    d = env["report"]["modules"]["m"]["diagnostics"][0]
    assert d["message"] == "__SCRIPT__ __STYLE__ __CSP__ __DATA__"
    assert "__CSP__" not in html.split('id="od-data"')[0]


def _sha(text: str) -> str:
    return "sha256-" + base64.b64encode(
        hashlib.sha256(text.encode("utf-8")).digest()
    ).decode("ascii")


def test_csp_hashes_match_the_inline_style_and_script():
    html = render_html_report(make_payload([make_diag()]), meta=META).html
    csp = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', html
    ).group(1)
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    assert f"script-src '{_sha(script)}'" in csp
    assert f"style-src '{_sha(style)}'" in csp
    assert csp.startswith("default-src 'none';")
    for directive in ("img-src data:", "base-uri 'none'", "form-action 'none'"):
        assert directive in csp


def test_page_is_self_contained():
    html = render_html_report(make_payload([make_diag()]), meta=META).html
    parser = _Collect()
    parser.feed(html)
    tags = [t for t, _ in parser.tags]
    assert "link" not in tags
    assert tags.count("style") == 1
    assert tags.count("script") == 2
    for tag, attrs in parser.tags:
        assert "src" not in attrs and "href" not in attrs, (tag, attrs)
    assert html.lstrip().lower().startswith("<!doctype html>")


def test_assets_are_readable_through_importlib_resources():
    folder = resources.files("odoo_doctor.reporters.html")
    for name in ("template.html", "report.css", "report.js"):
        assert folder.joinpath(name).is_file(), name
    css = folder.joinpath("report.css").read_text(encoding="utf-8")
    js = folder.joinpath("report.js").read_text(encoding="utf-8")
    assert "</style" not in css.lower()
    assert "</script" not in js.lower()


def _css_rule_body(css: str, selector: str) -> str:
    """Declarations of the first top-level rule whose selector list is exactly `selector`."""
    for match in re.finditer(r"(^|\n)([^{}\n@][^{}]*)\{([^{}]*)\}", css):
        if match.group(2).strip() == selector:
            return match.group(3)
    raise AssertionError(f"no CSS rule for {selector!r}")


@pytest.mark.parametrize("selector", ["h1", "code", ".muted"])
def test_long_unbroken_text_wraps_instead_of_widening_the_page(selector):
    # Found in a real browser at 360 px: long absolute paths (fix-first list) and a long
    # project name widened the layout viewport, so the page scrolled sideways.
    css = (
        resources.files("odoo_doctor.reporters.html")
        .joinpath("report.css")
        .read_text(encoding="utf-8")
    )
    body = _css_rule_body(css, selector)
    assert "overflow-wrap: anywhere" in body or "word-break: break-all" in body


def test_select_never_exceeds_its_container():
    # A module filter listing 271 long names was 383 px wide at a 360 px viewport.
    css = (
        resources.files("odoo_doctor.reporters.html")
        .joinpath("report.css")
        .read_text(encoding="utf-8")
    )
    body = _css_rule_body(css, 'button, select, input[type="search"]')
    assert "max-width: 100%" in body
