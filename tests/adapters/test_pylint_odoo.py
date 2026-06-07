# tests/adapters/test_pylint_odoo.py
"""Tests for Pylint-Odoo adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter


def test_pylint_adapter_name():
    adapter = PylintOdooAdapter()
    assert adapter.name == "pylint-odoo"


def test_pylint_parse_output(fixtures_dir: Path):
    adapter = PylintOdooAdapter()
    raw_text = (fixtures_dir / "adapters" / "pylint_odoo_output.txt").read_text()
    diags = adapter._parse_output(raw_text, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "pylint-odoo" for d in diags)

    sql = next(d for d in diags if d.rule == "E8102")
    assert sql.category == "Security"
    assert sql.tier == "P0"

    trans = next(d for d in diags if d.rule == "W8120")
    assert trans.category == "Maintainability"


def test_pylint_unmapped_rule():
    adapter = PylintOdooAdapter()
    raw_text = "f.py:1:0: C9999: Unknown rule (unknown-rule)\n"
    diags = adapter._parse_output(raw_text, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].confidence == "low"


def test_pylint_adapter_warns_when_missing(monkeypatch, tmp_path: Path):
    adapter = PylintOdooAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: False)
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "adapter-pylint-odoo-warning"
    assert "not found" in diags[0].message


def test_pylint_adapter_warns_on_timeout(monkeypatch, tmp_path: Path):
    adapter = PylintOdooAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pylint", timeout=120)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert "timeout" in diags[0].title


def test_pylint_adapter_warns_on_missing_plugin(monkeypatch, tmp_path: Path):
    adapter = PylintOdooAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 32, stdout="", stderr="No module named pylint_odoo"
        ),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert "missing plugin" in diags[0].title
