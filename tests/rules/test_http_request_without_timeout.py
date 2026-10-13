"""http-request-without-timeout: requests / urlopen calls that can block a worker forever."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.performance.http_request_without_timeout import (
    check_http_request_without_timeout,
)


def _check(tmp_path: Path, source: str, where="models/m.py"):
    path = tmp_path / "mod" / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return check_http_request_without_timeout(path, "mod", "17.0")


def test_requests_call_without_timeout_is_flagged(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import requests\n\n\ndef f(url):\n    return requests.post(url, json={})\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "http-request-without-timeout",
        "P2",
        "Performance",
        "high",
    )
    assert d.line == 5
    assert "timeout" in d.help


def test_multiline_call_is_flagged_once(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import requests\n\n\ndef f(url):\n    return requests.get(\n        url,\n"
        "        headers={},\n    )\n",
    )
    assert [d.line for d in diags] == [5]


@pytest.mark.parametrize(
    "call",
    [
        "requests.get(url, timeout=10)",
        "requests.get(url, timeout=(3, 10))",
        "requests.get(url, **options)",
        "requests.get(*args)",
        "requests.codes.ok",
        "requests.exceptions.HTTPError()",
        "json.get(url)",
        "self.get(url)",
    ],
)
def test_calls_that_are_fine_or_not_http_are_not_flagged(tmp_path: Path, call: str):
    src = f"import json\nimport requests\n\n\ndef f(self, url, options, args):\n    {call}\n"
    assert _check(tmp_path, src) == []


def test_aliases_and_from_imports_are_followed(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import requests as rq\nfrom requests import post as send\n\n\n"
        "def f(url):\n    rq.get(url)\n    send(url)\n",
    )
    assert [d.line for d in diags] == [6, 7]


def test_session_calls_are_flagged(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import requests\n\n\nclass C:\n    def __init__(self):\n"
        "        self.session = requests.Session()\n\n    def go(self, url):\n"
        "        s = requests.Session()\n        s.get(url, timeout=5)\n"
        "        s.post(url)\n        return self.session.get(url)\n",
    )
    assert [d.line for d in diags] == [11, 12]


def test_urlopen_without_timeout(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import urllib.request\nfrom urllib.request import urlopen\n\n\n"
        "def f(url):\n    urllib.request.urlopen(url)\n    urlopen(url)\n"
        "    urlopen(url, None, 5)\n    urlopen(url, timeout=5)\n",
    )
    assert [d.line for d in diags] == [6, 7]


def test_tests_and_migrations_are_skipped(tmp_path: Path):
    src = "import requests\nrequests.get('http://x')\n"
    assert _check(tmp_path, src, where="tests/test_a.py") == []
    assert _check(tmp_path, src, where="migrations/17.0.1.0/post.py") == []
