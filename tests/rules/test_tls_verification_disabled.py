"""tls-verification-disabled: certificate or hostname verification switched off."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.security.tls_verification_disabled import (
    check_tls_verification_disabled,
)


def _check(tmp_path: Path, source: str, where="models/m.py"):
    path = tmp_path / "mod" / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return check_tls_verification_disabled(path, "mod", "17.0")


def test_requests_verify_false_is_flagged(tmp_path: Path):
    diags = _check(
        tmp_path,
        "import requests\n\n\ndef f(url):\n    return requests.get(url, verify=False)\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "tls-verification-disabled",
        "P1",
        "Security",
        "high",
    )
    assert d.line == 5
    assert "verify=" in d.help


@pytest.mark.parametrize(
    "line",
    [
        "session.verify = False",
        "ctx.check_hostname = False",
        "ctx.verify_mode = ssl.CERT_NONE",
        "ctx = ssl._create_unverified_context()",
        "ssl._create_default_https_context = ssl._create_unverified_context",
    ],
)
def test_other_ways_to_disable_verification(tmp_path: Path, line: str):
    diags = _check(
        tmp_path, f"import ssl\nimport requests\n\n\ndef f(session, ctx):\n    {line}\n"
    )
    assert len(diags) == 1
    assert diags[0].confidence == "high"


def test_verify_false_without_a_network_import_is_medium(tmp_path: Path):
    diags = _check(tmp_path, "def f(x):\n    return x.check(verify=False)\n")
    assert [d.confidence for d in diags] == ["medium"]


@pytest.mark.parametrize(
    "line",
    [
        "requests.get(url, verify=True)",
        "requests.get(url, verify='/etc/ssl/ca.pem')",
        "requests.get(url, verify=verify)",
        "ctx.check_hostname = True",
        "ctx.verify_mode = ssl.CERT_REQUIRED",
    ],
)
def test_verification_left_on_is_not_flagged(tmp_path: Path, line: str):
    src = f"import ssl\nimport requests\n\n\ndef f(url, verify, ctx):\n    {line}\n"
    assert _check(tmp_path, src) == []


def test_tests_are_skipped(tmp_path: Path):
    src = "import requests\nrequests.get('http://x', verify=False)\n"
    assert _check(tmp_path, src, where="tests/test_a.py") == []
