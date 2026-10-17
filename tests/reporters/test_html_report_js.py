"""report.js: forbidden constructs (static) and a smoke run against a fake DOM (Node)."""

from __future__ import annotations

import json
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

from odoo_doctor.reporters.html_report import render_html_report
from tests.reporters.test_html_report import (
    EVIL,
    META,
    history_record,
    make_diag,
    make_payload,
)

HARNESS = Path(__file__).with_name("html_smoke.js")
NODE = shutil.which("node")
BS = chr(92)

FORBIDDEN_JS = [
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
    "setTimeout(" + '"',
    "setInterval(" + '"',
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "sendBeacon",
    "cssText",
    ".style",
    'setAttribute("style"',
    "DOMParser",
    "createContextualFragment",
    "srcdoc",
    ".src =",
    ".src=",
]


def _js() -> str:
    folder = resources.files("odoo_doctor.reporters.html")
    return folder.joinpath("report.js").read_text(encoding="utf-8")


def test_report_js_uses_none_of_the_forbidden_constructs():
    js = _js()
    for needle in FORBIDDEN_JS:
        assert needle not in js, needle


def test_report_js_has_no_style_attribute_or_inline_handler_strings():
    js = _js()
    assert "style=" not in js and "onclick=" not in js and BS + "u" not in js


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_report_js_is_syntactically_valid(tmp_path: Path):
    target = tmp_path / "report.js"
    target.write_text(_js(), encoding="utf-8")
    done = subprocess.run(
        [NODE, "--check", str(target)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


def _smoke(tmp_path: Path, html: str) -> dict:
    page = tmp_path / "report.html"
    page.write_bytes(html.encode("utf-8"))
    done = subprocess.run(
        [NODE, str(HARNESS), str(page)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_renders_sections_and_toggles_low_findings(tmp_path: Path):
    diags = [
        make_diag(line=1),
        make_diag(line=2, tier="P2", message=EVIL, rule="sudo-without-comment"),
        make_diag(line=3, confidence="low", rule="missing-ondelete"),
        make_diag(line=4, confidence="low", module="n"),
    ]
    html = render_html_report(
        make_payload(diags),
        meta=META,
        history=[history_record(80.0), history_record(90.0)],
    ).html
    out = _smoke(tmp_path, html)
    assert out["rowsDefault"] == 2
    assert out["rowsWithLow"] == 4
    assert out["rowsModuleFilter"] == 1
    assert "Findings" in out["text"] and "Fix first" in out["text"]
    assert "Modules: 2 · Findings: 4" in out["text"]
    assert "Rule reference" in out["text"] and "Project" in out["text"]
    assert "May span several branches." in out["text"]
    assert EVIL in out["text"]  # shown as text, never as markup
    assert out["badElements"] == 0


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_trend_table_follows_the_selected_series(tmp_path: Path):
    first = history_record(80.0)
    second = history_record(90.0)
    second["modules"]["n"] = {"overall": 70.0, "label": "Needs work"}
    diags = [make_diag(), make_diag(module="n", line=2)]
    html = render_html_report(
        make_payload(diags), meta=META, history=[first, second]
    ).html
    out = _smoke(tmp_path, html)
    rows = out["trendRows"]
    assert rows[0] == ["Time", "Branch", "Commit", "Score (n)"]
    assert rows[1][3] == "–" and rows[2][3] == "70.0"  # module n missing in scan 1


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_pagination_shows_200_then_the_rest(tmp_path: Path):
    diags = [make_diag(line=i + 1) for i in range(250)]
    html = render_html_report(make_payload(diags), meta=META).html
    out = _smoke(tmp_path, html)
    assert out["rowsDefault"] == 200
    assert out["moreHiddenDefault"] is False
    assert out["rowsAfterMore"] == 250
    assert out["moreHiddenAfter"] is True


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_zero_findings_and_no_history(tmp_path: Path):
    html = render_html_report(make_payload([]), meta=META).html
    out = _smoke(tmp_path, html)
    assert out["rowsDefault"] == 0
    assert "No findings" in out["text"]
    assert "trend" not in out["text"].lower()


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_single_history_point_asks_for_a_second_scan(tmp_path: Path):
    html = render_html_report(
        make_payload([make_diag()]), meta=META, history=[history_record(90.0)]
    ).html
    out = _smoke(tmp_path, html)
    assert "At least 2 scans are needed for a trend." in out["text"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_notes_truncation_and_partial_scope(tmp_path: Path):
    diags = [make_diag(line=i) for i in range(1, 4)] + [
        make_diag(line=10 + i, confidence="low", message="x" * 400) for i in range(40)
    ]
    payload = make_payload(diags)
    full = render_html_report(payload, meta=META)
    meta = dict(META, scope={"partial": True, "diff": "origin/main", "modules": []})
    cut = render_html_report(payload, meta=meta, max_bytes=full.size - 1000)
    out = _smoke(tmp_path, cut.html)
    assert "40 low-confidence findings were not embedded" in out["text"]
    assert "Partial scan" in out["text"] and "origin/main" in out["text"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_only_https_rule_urls_become_links(tmp_path: Path):
    diags = [
        make_diag(line=1, rule="rule-js", url="javascript:alert(1)"),
        make_diag(line=2, rule="rule-http", url="http://x"),
        make_diag(line=3, rule="rule-ok", url="https://ok"),
    ]
    html = render_html_report(make_payload(diags), meta=META).html
    out = _smoke(tmp_path, html)
    nodes = out["ruleNodes"]
    links = [n for n in nodes if n["tag"] == "a"]
    assert len(nodes) == 3 and len(links) == 1
    assert links[0]["href"] == "https://ok" and links[0]["text"] == "rule-ok"
    assert "noopener" in links[0]["rel"] and "noreferrer" in links[0]["rel"]
    plain = sorted(n["text"] for n in nodes if n["tag"] == "span")
    assert plain == ["rule-http", "rule-js"]
    assert all(n["href"] is None for n in nodes if n["tag"] == "span")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize(
    ("dirty", "expected"),
    [
        (True, "main @ abc1234 (uncommitted changes)"),
        (False, "main @ abc1234"),
        (None, "main @ abc1234"),
    ],
)
def test_smoke_header_marks_uncommitted_changes_only_when_dirty(
    tmp_path: Path, dirty, expected
):
    html = render_html_report(
        make_payload([make_diag()]), meta={**META, "dirty": dirty}
    ).html
    text = _smoke(tmp_path, html)["text"]
    assert expected in text
    assert ("uncommitted changes" in text) is bool(dirty)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_smoke_header_shows_the_secondary_scores(tmp_path: Path):
    payload = make_payload([make_diag()])
    payload["project_score"].update({"weighted": 92.2, "with_medium": 90.9})
    text = _smoke(tmp_path, render_html_report(payload, meta=META).html)["text"]
    assert "Weighted by code size: 92.2" in text
    assert "Counting medium findings: 90.9" in text
