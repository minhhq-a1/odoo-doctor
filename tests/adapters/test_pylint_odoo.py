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
    assert len(diags) == 3
    assert all(d.source == "pylint-odoo" for d in diags)

    commit = next(d for d in diags if d.rule == "E8102")
    assert commit.category == "Correctness"
    assert commit.tier == "P2"

    sql = next(d for d in diags if d.rule == "E8103")
    assert sql.category == "Security"
    assert sql.tier == "P0"

    trans = next(d for d in diags if d.rule == "W8120")
    assert trans.category == "Maintainability"


def test_pylint_e8102_is_invalid_commit_not_security():
    adapter = PylintOdooAdapter()
    raw = "models/sale.py:25:0: E8102: Use of cr.commit() (invalid-commit)\n"
    d = adapter._parse_output(raw, module_name="m", odoo_version="17.0")[0]
    assert d.rule == "E8102"
    assert d.category == "Correctness"
    assert d.tier == "P2"


def test_pylint_e8103_is_sql_injection_p0():
    adapter = PylintOdooAdapter()
    raw = "models/sale.py:30:0: E8103: SQL injection risk (sql-injection)\n"
    d = adapter._parse_output(raw, module_name="m", odoo_version="17.0")[0]
    assert d.rule == "E8103"
    assert d.category == "Security"
    assert d.tier == "P0"
    assert d.confidence == "high"


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


def test_pylint_adapter_warns_on_nonzero_exit_with_no_findings(
    monkeypatch, tmp_path: Path
):
    adapter = PylintOdooAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    # Exit 32 = pylint usage error; stdout has nothing parseable
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 32, stdout="", stderr="usage error"
        ),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "adapter-pylint-odoo-warning"
    assert "process error" in diags[0].title


def test_pylint_adapter_keeps_findings_on_nonzero_exit(monkeypatch, tmp_path: Path):
    # Pylint exits non-zero (bitmask) when it reports messages — that is success
    adapter = PylintOdooAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)
    stdout = "models/sale.py:10:0: E8102: Use of cr.commit() (invalid-commit)\n"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 2, stdout=stdout, stderr=""),
    )
    diags = adapter.run(tmp_path, "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "E8102"


def _addon_with_hostile_pylintrc(root: Path) -> tuple[Path, Path]:
    """An addon whose repo ships an inert init-hook that would write a marker."""
    marker = root / "MARKER"
    repo = root / "repo"
    mod = repo / "m"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text("{'name': 'm'}\n")
    (mod / "__init__.py").write_text("")
    hook = f"open({str(marker)!r}, 'w').write('x')"
    (repo / ".pylintrc").write_text(f"[MAIN]\ninit-hook={hook}\n")
    (repo / "pyproject.toml").write_text(f'[tool.pylint.main]\ninit-hook = "{hook}"\n')
    return repo, marker


def test_pylint_command_ignores_repo_config(tmp_path: Path, monkeypatch):
    import odoo_doctor.adapters.pylint_odoo.adapter as mod

    repo, _ = _addon_with_hostile_pylintrc(tmp_path)
    seen: dict = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        seen["rc_existed"] = Path(
            next(a for a in cmd if a.startswith("--rcfile=")).split("=", 1)[1]
        ).is_file()
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("PYTHONPATH", str(repo))
    monkeypatch.setenv("PYLINTRC", str(repo / ".pylintrc"))
    monkeypatch.setenv("HOME", str(repo))
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/pylint")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.chdir(repo)
    PylintOdooAdapter().run(repo / "m", "17.0")

    rc = next(a for a in seen["cmd"] if a.startswith("--rcfile="))
    assert seen["rc_existed"]
    assert not Path(rc.split("=", 1)[1]).resolve().is_relative_to(repo.resolve())
    assert not Path(seen["kw"]["cwd"]).resolve().is_relative_to(repo.resolve())
    env = seen["kw"]["env"]
    assert "GH_TOKEN" not in env and "PYTHONPATH" not in env and "PYLINTRC" not in env
    assert not Path(env["HOME"]).resolve().is_relative_to(repo.resolve())
    assert Path(seen["cmd"][-1]).is_absolute()


def test_pylint_does_not_execute_repo_init_hook(tmp_path: Path, monkeypatch):
    import shutil

    import pytest

    exe = shutil.which("pylint")
    probe = (
        subprocess.run(
            [exe, "--load-plugins=pylint_odoo", "--version"],
            capture_output=True,
            check=False,
        )
        if exe
        else None
    )
    if probe is None or probe.returncode != 0:
        pytest.skip("pylint with pylint_odoo is not installed")
    repo, marker = _addon_with_hostile_pylintrc(tmp_path)
    monkeypatch.chdir(repo)
    diags = PylintOdooAdapter().run((repo / "m").resolve(), "17.0")
    assert not marker.exists()
    assert any(not d.rule.startswith("adapter-") for d in diags)
