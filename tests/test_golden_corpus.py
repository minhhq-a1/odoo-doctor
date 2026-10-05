"""Golden corpus: scan small sample addons end to end and compare with a frozen answer.

Each directory under ``tests/corpus/`` is one case, scanned exactly like a user
would (``odoo-doctor scan <case> --json``). ``expected.json`` lists every finding as
``[rule, file, confidence]``, so the corpus guards both directions: findings we
must keep (true positives) and findings we must not produce (known false
positives). When a rule is intentionally changed, review the diff and refresh the
answers with::

    UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_doctor.cli.app import app

CORPUS = Path(__file__).parent / "corpus"
CASES = sorted(p.name for p in CORPUS.iterdir() if p.is_dir())

runner = CliRunner()


def _scan(case: str) -> list[list[str]]:
    case_dir = (CORPUS / case).resolve()
    result = runner.invoke(app, ["scan", str(case_dir), "--json"])
    assert result.exit_code in (0, 1), result.output
    report = json.loads(result.stdout)
    findings = [
        [d["rule"], os.path.relpath(d["file_path"], case_dir), d["confidence"]]
        for module in report["modules"].values()
        for d in module["diagnostics"]
    ]
    return sorted(findings)


def test_corpus_is_not_empty():
    assert CASES


@pytest.mark.parametrize("case", CASES)
def test_corpus_case_matches_golden(case: str):
    actual = _scan(case)
    golden = CORPUS / case / "expected.json"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(json.dumps(actual, indent=2) + "\n")
    assert golden.exists(), f"missing {golden}; run with UPDATE_GOLDEN=1 and review it"
    assert actual == json.loads(golden.read_text())
