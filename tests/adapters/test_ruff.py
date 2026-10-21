# tests/adapters/test_ruff.py
"""Tests for Ruff adapter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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


def _addon_with_hostile_ruff_config(root: Path) -> tuple[Path, Path]:
    """An addon whose repo config ignores F401 and sends the ruff cache elsewhere."""
    evil_cache = root / "evil_cache"
    repo = root / "repo"
    mod = repo / "m"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text("{'name': 'm'}\n")
    (mod / "__init__.py").write_text("")
    (mod / "models.py").write_text("import os\n")
    (repo / "ruff.toml").write_text(
        f'cache-dir = "{evil_cache}"\n[lint]\nignore = ["F401"]\n'
    )
    return repo, evil_cache


def test_ruff_command_is_isolated_from_the_repo(tmp_path: Path, monkeypatch):
    import odoo_doctor.adapters.ruff.adapter as mod

    repo, _ = _addon_with_hostile_ruff_config(tmp_path)
    seen: dict = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("RUFF_CACHE_DIR", str(repo / "c"))
    monkeypatch.setenv("HOME", str(repo))
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/ruff")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.chdir(repo)
    RuffAdapter().run(repo / "m", "17.0")

    cmd = seen["cmd"]
    assert "--isolated" in cmd and "--no-cache" in cmd
    assert "--no-respect-gitignore" in cmd and "--config" not in cmd
    assert Path(cmd[-1]).is_absolute()
    assert seen["kw"]["stdin"] == subprocess.DEVNULL
    assert not Path(seen["kw"]["cwd"]).resolve().is_relative_to(repo.resolve())
    env = seen["kw"]["env"]
    assert "GH_TOKEN" not in env and "RUFF_CACHE_DIR" not in env
    assert not Path(env["HOME"]).resolve().is_relative_to(repo.resolve())


def _run_in(repo: Path, monkeypatch, cwd: Path) -> set[str]:
    monkeypatch.chdir(cwd)
    return {d.rule for d in RuffAdapter().run(repo / "m", "17.0")}


def test_ruff_ignores_the_repo_config_and_writes_no_cache(
    tmp_path: Path, monkeypatch, capsys
):
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not installed")
    repo, evil_cache = _addon_with_hostile_ruff_config(tmp_path)
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    assert "F401" in _run_in(repo, monkeypatch, elsewhere)  # ruff.toml not applied
    assert "ruff configuration is ignored" in capsys.readouterr().err
    assert not evil_cache.exists()  # the repo's cache-dir was not honoured
    assert not list(repo.rglob(".ruff_cache"))
    # pyproject.toml [tool.ruff] is ignored the same way, from any cwd
    (repo / "ruff.toml").unlink()
    (repo / "pyproject.toml").write_text('[tool.ruff.lint]\nignore = ["F401"]\n')
    assert "F401" in _run_in(repo, monkeypatch, elsewhere)


def test_ruff_ignores_a_config_that_tries_to_hide_everything(
    tmp_path: Path, monkeypatch
):
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not installed")
    repo, _ = _addon_with_hostile_ruff_config(tmp_path)
    (repo / "ruff.toml").write_text(
        'exclude = ["*"]\nextend-exclude = ["m"]\nline-length = 1\n'
        '[lint]\nselect = []\nignore = ["ALL"]\n'
        '[lint.per-file-ignores]\n"*" = ["ALL"]\n'
    )
    (repo / ".gitignore").write_text("m/models.py\n")
    (repo / ".ignore").write_text("m/models.py\n")
    assert "F401" in _run_in(repo, monkeypatch, tmp_path)  # models.py still linted


def test_ruff_never_reads_an_extend_to_a_hostile_path(tmp_path: Path, monkeypatch):
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not installed")
    repo, _ = _addon_with_hostile_ruff_config(tmp_path)
    (repo / "ruff.toml").write_text('extend = "/dev/zero"\n')
    diags = RuffAdapter().run(repo / "m", "17.0")
    assert "F401" in {d.rule for d in diags}
    assert not [d for d in diags if d.rule == "adapter-ruff-warning"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no os.mkfifo")
@pytest.mark.parametrize("kind", ["fifo", "dev-zero"])
def test_ruff_does_not_hang_on_a_special_extend_target(
    tmp_path: Path, capsys, kind: str
):
    import time

    if shutil.which("ruff") is None:
        pytest.skip("ruff is not installed")
    repo = tmp_path / "repo"
    (repo / "m").mkdir(parents=True)
    (repo / "m" / "a.py").write_text("import os\n")
    (repo / "ruff.toml").write_text('extend = "evil.toml"\n')
    if kind == "fifo":
        os.mkfifo(repo / "evil.toml")
    else:
        (repo / "evil.toml").symlink_to("/dev/zero")
    start = time.monotonic()
    diags = RuffAdapter().run(repo / "m", "17.0")
    RuffAdapter().run(repo / "m", "17.0")
    assert time.monotonic() - start < 20
    assert "F401" in {d.rule for d in diags}
    assert not [d for d in diags if d.rule == "adapter-ruff-warning"]
    err = capsys.readouterr().err
    # said once per process, not per run or per adapter instance
    assert err.count("ruff configuration is ignored") == 1
    assert "ruff.toml" in err


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no os.mkfifo")
def test_ruff_does_not_hang_on_a_fifo_named_py(tmp_path: Path, monkeypatch):
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not installed")
    repo, _ = _addon_with_hostile_ruff_config(tmp_path)
    os.mkfifo(repo / "m" / "pipe.py")
    diags = RuffAdapter().run(
        repo / "m", "17.0"
    )  # blocks (60 s timeout warning) if broken
    assert "F401" in {d.rule for d in diags}
    assert not [d for d in diags if d.rule == "adapter-ruff-warning"]
