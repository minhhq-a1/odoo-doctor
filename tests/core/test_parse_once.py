"""Each Python file is read and parsed once, not once per rule (0.6.0 performance)."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from odoo_doctor.core import source as source_mod
from odoo_doctor.core.config import load_config
from odoo_doctor.core.scanner import collect_scores
from odoo_doctor.core.source import clear_source_cache, parse_python, read_source
from odoo_doctor.rules import suppression
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.security import raw_sql_interpolation


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_source_cache()
    yield
    clear_source_cache()


@pytest.fixture
def count_parses(monkeypatch):
    calls = {"n": 0}
    real = ast.parse

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(ast, "parse", counting)
    return calls


# --- parse_python / read_source -----------------------------------------------


def test_parse_python_parses_a_file_once(tmp_path: Path, count_parses):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    first = parse_python(f)
    second = parse_python(f)
    assert isinstance(first, ast.Module)
    assert first is second
    assert count_parses["n"] == 1


def test_parse_python_sees_a_rewritten_file(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    assert len(parse_python(f).body) == 1
    f.write_text("x = 1\ny = 2\nz = 3\n")
    os.utime(f, ns=(1, 1))  # even an identical mtime must not hide a size change
    assert len(parse_python(f).body) == 3


def test_parse_python_returns_none_on_syntax_error(tmp_path: Path):
    f = tmp_path / "bad.py"
    f.write_text("def (:\n")
    assert parse_python(f) is None


def test_parse_python_returns_none_for_missing_file(tmp_path: Path):
    assert parse_python(tmp_path / "nope.py") is None
    assert read_source(tmp_path / "nope.py") is None


def test_read_source_is_cached_but_follows_changes(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\n")
    assert read_source(f) == "a = 1\n"
    f.write_text("a = 1000\n")
    assert read_source(f) == "a = 1000\n"


def test_read_source_still_tolerates_non_utf8(tmp_path: Path):
    f = tmp_path / "enc.py"
    f.write_bytes(b"# -*- coding: latin-1 -*-\nNAME = '\xe9'\n")
    assert "NAME" in read_source(f)


def test_cache_is_bounded(tmp_path: Path):
    for i in range(source_mod._CACHE_SIZE * 3):
        f = tmp_path / f"f{i}.py"
        f.write_text(f"x = {i}\n")
        parse_python(f)
    assert source_mod._parse.cache_info().currsize <= source_mod._CACHE_SIZE


# --- a whole scan -------------------------------------------------------------


def _write_addon(root: Path, files: int) -> None:
    mod = root / "mod"
    (mod / "models").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        '{"name": "mod", "version": "17.0.1.0.0", "depends": ["base"], '
        '"data": [], "license": "LGPL-3"}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    imports = ""
    for i in range(files):
        imports += f"from . import m{i}\n"
        (mod / "models" / f"m{i}.py").write_text(
            "from odoo import fields, models\n\n\n"
            f"class M{i}(models.Model):\n"
            f'    _name = "mod.m{i}"\n'
            '    _description = "M"\n'
            '    name = fields.Char(string="Name")\n\n'
            "    def run(self, ids):\n"
            "        for i in ids:\n"
            '            self.env["res.partner"].search([("id", "=", i)])\n'
        )
    (mod / "models" / "__init__.py").write_text(imports)


def test_scan_parses_each_python_file_a_bounded_number_of_times(
    tmp_path: Path, count_parses
):
    files = 8
    _write_addon(tmp_path, files)
    (tmp_path / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    cfg = load_config(tmp_path)
    collect_scores([tmp_path], cfg, "17.0")
    py_files = len(list(tmp_path.rglob("*.py")))
    # graph build (models + controllers share one parse) + one parse in the rule
    # phase. Before 0.6.0 this was ~11 parses per file.
    assert count_parses["n"] <= 2 * py_files + 2, (count_parses["n"], py_files)


def test_diagnostics_keep_rule_major_order(tmp_path: Path):
    """Reordering the loops (file-major) must not change the output order."""
    _write_addon(tmp_path, 3)
    (tmp_path / "odoo-doctor.toml").write_text(
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    cfg = load_config(tmp_path)
    diags, _ = collect_scores([tmp_path], cfg, "17.0")
    rule_order = [m.name for m, _ in default_registry.get_rules(needs_context=False)]
    native_file_rules = [d.rule for d in diags if d.rule in rule_order]
    positions = [rule_order.index(r) for r in native_file_rules]
    assert positions == sorted(positions), native_file_rules


# --- step 2: no tokenizing when there is nothing to find ------------------------


def test_raw_sql_does_not_tokenize_files_without_a_pylint_marker(
    tmp_path: Path, monkeypatch
):
    calls = {"n": 0}
    real = raw_sql_interpolation.tokenize.generate_tokens

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(raw_sql_interpolation.tokenize, "generate_tokens", counting)
    f = tmp_path / "m.py"
    f.write_text('def run(self, w):\n    self.env.cr.execute(f"SELECT {w}")\n')
    assert len(raw_sql_interpolation.check_raw_sql_interpolation(f, "m", "17.0")) == 1
    assert calls["n"] == 0


def test_raw_sql_still_honours_the_pylint_marker(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text(
        "def run(self, w):\n"
        "    # pylint: disable=sql-injection\n"
        '    self.env.cr.execute(f"SELECT {w}")\n'
    )
    assert raw_sql_interpolation.check_raw_sql_interpolation(f, "m", "17.0") == []


def test_suppression_scan_skips_files_without_the_marker(tmp_path: Path, monkeypatch):
    calls = {"n": 0}
    real = suppression.tokenize.tokenize

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(suppression.tokenize, "tokenize", counting)
    plain = tmp_path / "plain.py"
    plain.write_text("x = 1\n")
    assert suppression.scan_python_suppressions(plain) == set()
    assert calls["n"] == 0

    marked = tmp_path / "marked.py"
    marked.write_text("# odoo-doctor: disable=eval-usage\nx = eval(y)\n")
    assert suppression.scan_python_suppressions(marked) == {
        (str(marked), 2, "eval-usage")
    }
    assert calls["n"] == 1
