# tests/adapters/test_ruff.py
"""Tests for Ruff adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from odoo_doctor.adapters.ruff.adapter import RuffAdapter


def test_ruff_adapter_is_backend_adapter():
    adapter = RuffAdapter()
    assert adapter.name == "ruff"


def test_ruff_adapter_parse_output(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "ruff" for d in diags)
    assert diags[0].rule == "E501"


def test_ruff_adapter_applies_rule_mapping(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    e501 = next(d for d in diags if d.rule == "E501")
    assert e501.category == "Maintainability"
    assert e501.tier == "P3"


def test_ruff_adapter_unmapped_rule():
    adapter = RuffAdapter()
    raw = [
        {
            "code": "UNKNOWN999",
            "message": "something",
            "filename": "f.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 1},
        }
    ]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].tier == "P3"
    assert diags[0].confidence == "low"


def test_ruff_adapter_filters_f401_in_init():
    adapter = RuffAdapter()
    raw = [
        {
            "code": "F401",
            "message": "unused import",
            "filename": "__init__.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 1},
        },
        {
            "code": "F401",
            "message": "unused import",
            "filename": "models/res_partner.py",
            "location": {"row": 5, "column": 1},
            "end_location": {"row": 5, "column": 1},
        },
    ]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    # F401 in __init__.py is filtered out, but the one in res_partner.py is kept
    assert len(diags) == 1
    assert diags[0].file_path == "models/res_partner.py"


def test_ruff_adapter_warns_when_missing(monkeypatch, tmp_path: Path):
    adapter = RuffAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: False)
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "adapter-ruff-warning"
    assert "not found" in diags[0].message


def test_ruff_adapter_warns_on_timeout(monkeypatch, tmp_path: Path):
    adapter = RuffAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=60)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert "timeout" in diags[0].title


def test_ruff_adapter_warns_on_invalid_json(monkeypatch, tmp_path: Path):
    adapter = RuffAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout="not-json", stderr=""
        ),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert "parse failure" in diags[0].title


def test_ruff_adapter_tolerates_null_fields(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads(
        (fixtures_dir / "adapters" / "ruff_output_null_fields.json").read_text()
    )
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    # Both records survive — the null-field one degrades to defaults, no crash
    assert len(diags) == 2
    null_diag = next(d for d in diags if d.rule == "")
    assert null_diag.file_path == ""
    assert null_diag.line == 0
    assert null_diag.column == 0
    assert null_diag.message == ""
    valid = next(d for d in diags if d.rule == "E501")
    assert valid.line == 15


def test_ruff_adapter_skips_non_dict_record():
    adapter = RuffAdapter()
    raw = [
        None,
        {
            "code": "E501",
            "message": "x",
            "filename": "a.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 2},
        },
    ]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    # The null record is dropped; the valid one is kept
    assert len(diags) == 1
    assert diags[0].rule == "E501"


def test_ruff_adapter_warns_on_nonzero_exit_with_no_findings(
    monkeypatch, tmp_path: Path
):
    adapter = RuffAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 2, stdout="", stderr="boom"),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "adapter-ruff-warning"
    assert "process error" in diags[0].title
    assert diags[0].severity == "warning"


def test_ruff_adapter_keeps_findings_on_exit_1(monkeypatch, tmp_path: Path):
    # Ruff exits 1 when violations exist — this is success, not failure
    adapter = RuffAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    payload = json.dumps(
        [
            {
                "code": "E501",
                "message": "long",
                "filename": "a.py",
                "location": {"row": 1, "column": 1},
                "end_location": {"row": 1, "column": 2},
            }
        ]
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout=payload, stderr=""),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "E501"
