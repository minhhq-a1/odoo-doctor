"""A scan never blocks on, or reads without bound from, a special or huge file in the repo.

Every scan runs in a child process with a timeout: opening a FIFO blocks forever, and a
test that did that in-process would hang the whole suite instead of failing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GOOD_PY = "def run(self, expr):\n    return eval(expr)\n"
MANIFEST = "{'name': 'Mod', 'version': '17.0.1.0.0', 'depends': ['base'], %s}"
_TIMEOUT = 30

needs_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no os.mkfifo")
needs_dev_zero = pytest.mark.skipif(
    not Path("/dev/zero").exists(), reason="no /dev/zero"
)


def _addon(root: Path, manifest: str | None = None) -> Path:
    mod = root / "mod"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(manifest or MANIFEST % "'data': []")
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import good\n")
    (mod / "models" / "good.py").write_text(GOOD_PY)
    return mod


def _scan(root: Path) -> tuple[list[dict], list[str]]:
    """(findings, WARN lines); fails (instead of hanging) when the scan blocks."""
    code = "import sys; from odoo_doctor.cli.app import app; app()"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, "scan", str(root), "--json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"the scan blocked for more than {_TIMEOUT} s")
    assert proc.returncode in (0, 1), proc.stderr
    report = json.loads(proc.stdout)
    findings = [d for m in report["modules"].values() for d in m["diagnostics"]]
    warns = [
        ln
        for ln in proc.stderr.splitlines()
        if ln.startswith("[WARN] ") and "more skipped" not in ln
    ]
    return findings, warns


def _eval_files(findings: list[dict]) -> set[str]:
    return {Path(d["file_path"]).name for d in findings if d["rule"] == "eval-usage"}


@needs_fifo
def test_fifo_named_py(tmp_path: Path):
    mod = _addon(tmp_path)
    os.mkfifo(mod / "models" / "pipe.py")
    findings, warns = _scan(tmp_path)
    assert _eval_files(findings) == {"good.py"}
    assert len([w for w in warns if "pipe.py" in w]) == 1, warns


@needs_fifo
def test_fifo_as_manifest_and_data_files(tmp_path: Path):
    mod = _addon(
        tmp_path, MANIFEST % "'data': ['views/v.xml', 'security/ir.model.access.csv']"
    )
    (mod / "views").mkdir()
    (mod / "security").mkdir()
    os.mkfifo(mod / "views" / "v.xml")
    os.mkfifo(mod / "security" / "ir.model.access.csv")
    other = tmp_path / "other"
    other.mkdir()
    os.mkfifo(other / "__manifest__.py")
    findings, warns = _scan(tmp_path)
    assert _eval_files(findings) == {"good.py"}
    for name in ("v.xml", "ir.model.access.csv", "__manifest__.py"):
        assert [w for w in warns if name in w], (name, warns)


@needs_dev_zero
def test_symlink_to_dev_zero(tmp_path: Path):
    mod = _addon(tmp_path)
    (mod / "models" / "zero.py").symlink_to("/dev/zero")
    findings, warns = _scan(tmp_path)
    assert _eval_files(findings) == {"good.py"}
    assert len([w for w in warns if "zero.py" in w]) == 1, warns


@needs_fifo
def test_symlink_to_fifo(tmp_path: Path):
    mod = _addon(tmp_path)
    os.mkfifo(tmp_path / "pipe")
    (mod / "models" / "link.py").symlink_to(tmp_path / "pipe")
    findings, warns = _scan(tmp_path)
    assert _eval_files(findings) == {"good.py"}
    assert len([w for w in warns if "link.py" in w]) == 1, warns


def test_oversized_file_is_skipped_with_a_warning(tmp_path: Path):
    mod = _addon(tmp_path)
    (mod / "models" / "big.py").write_bytes(
        GOOD_PY.encode() + b"#" * (17 * 1024 * 1024)
    )
    findings, warns = _scan(tmp_path)
    assert _eval_files(findings) == {"good.py"}
    assert len([w for w in warns if "big.py" in w]) == 1, warns


def test_symlink_inside_and_outside_the_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mod = _addon(repo)
    outside = tmp_path / "outside.py"
    outside.write_text(GOOD_PY)
    (mod / "models" / "inside.py").symlink_to(mod / "models" / "good.py")
    (mod / "models" / "escape.py").symlink_to(outside)
    findings, warns = _scan(repo)
    # findings carry resolved paths, so the inside link is good.py again
    assert _eval_files(findings) == {"good.py"}
    assert len([w for w in warns if "escape.py" in w]) == 1, warns
    assert not [w for w in warns if "inside.py" in w], warns
