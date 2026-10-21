"""A scan that reuses the previous one (the language server's) equals a scan from scratch."""

from __future__ import annotations

import dataclasses
import shutil
import time
from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (registers the rules)
from odoo_doctor.core.config import load_config
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.reuse import ScanReuse, Stamper
from odoo_doctor.core.scanner import collect_scores

SQL = "        self.env.cr.execute(f\"SELECT 1 FROM t WHERE n = '{name}'\")\n"


def _module(root: Path, name: str, depends: list[str], model: str, body: str = SQL):
    mod = root / name
    (mod / "models").mkdir(parents=True)
    (mod / "views").mkdir()
    (mod / "__manifest__.py").write_text(
        f'{{"name": "{name}", "version": "17.0.1.0.0", "depends": {depends!r}, '
        f'"data": ["views/v.xml"], "license": "LGPL-3"}}'
    )
    (mod / "__init__.py").write_text("from . import models\n")
    (mod / "models" / "__init__.py").write_text("from . import m\n")
    (mod / "models" / "m.py").write_text(
        "from odoo import fields, models\n\n"
        f"class M(models.Model):\n    _name = '{model}'\n    _description = 'M'\n"
        "    title = fields.Char()\n\n"
        f"    def run(self, name):\n{body}"
    )
    (mod / "views" / "v.xml").write_text(
        '<odoo><record id="v" model="ir.ui.view"><field name="name">v</field>'
        f'<field name="model">{model}</field><field name="arch" type="xml">'
        '<form><field name="title"/></form></field></record></odoo>'
    )


def _project(root: Path) -> None:
    (root / "odoo-doctor.toml").write_text(
        '[odoo-doctor]\nodoo_version = "17.0"\n\n'
        "[adapters]\nruff = false\npylint_odoo = false\n"
    )
    _module(root, "base_x", ["base"], "x.base")
    # b's view shows a field of a model defined in base_x; c has nothing to do with them
    _module(root, "mod_b", ["base_x"], "x.b")
    (root / "mod_b" / "views" / "v.xml").write_text(
        '<odoo><record id="vb" model="ir.ui.view"><field name="name">v</field>'
        '<field name="model">x.base</field><field name="arch" type="xml">'
        '<form><field name="title"/></form></field></record></odoo>'
    )
    _module(root, "mod_c", ["base"], "x.c", body="        return 1\n")


def _scan(root: Path, reuse: ScanReuse | None):
    cfg = load_config(root)
    return collect_scores(
        addon_paths=[root],
        cfg=cfg,
        version=cfg.odoo_version or "unknown",
        config_root=root,
        reuse=reuse,
    )


def _same(root: Path, reuse: ScanReuse) -> list[Diagnostic]:
    diags, scores = _scan(root, reuse)
    full_diags, full_scores = _scan(root, None)
    assert diags == full_diags
    assert {k: dataclasses.asdict(v) for k, v in scores.items()} == {
        k: dataclasses.asdict(v) for k, v in full_scores.items()
    }
    return diags


def test_incremental_equals_full_after_edits(tmp_path: Path):
    root = tmp_path.resolve()
    _project(root)
    reuse = ScanReuse()
    first = _same(root, reuse)
    assert any(d.rule == "raw-sql-string-interpolation" for d in first)
    assert _same(root, reuse) == first  # nothing changed

    model_b = root / "mod_b" / "models" / "m.py"
    model_x = root / "base_x" / "models" / "m.py"

    model_b.write_text(model_b.read_text() + "\n# a comment\n")  # modify a file
    _same(root, reuse)

    new = root / "mod_c" / "models" / "extra.py"  # add a file with a finding
    new.write_text(
        "from odoo import models\n\nclass E(models.Model):\n    _name = 'x.e'\n"
        "    def f(self, n):\n        eval(n)\n"
    )
    assert any(d.rule == "eval-usage" for d in _same(root, reuse))
    new.unlink()  # delete it
    assert not any(d.rule == "eval-usage" for d in _same(root, reuse))

    shutil.copytree(root / "mod_c", root / "mod_d")  # add a module
    _same(root, reuse)
    shutil.rmtree(root / "mod_d")  # delete a module
    _same(root, reuse)

    manifest = root / "mod_c" / "__manifest__.py"  # change a dependency
    text = manifest.read_text()
    manifest.write_text(text.replace('["base"]', '["base", "base_x"]'))
    _same(root, reuse)
    manifest.write_text(text)
    _same(root, reuse)

    # a model another module's view shows loses the field: mod_b's finding changes
    before = {d.rule for d in _same(root, reuse) if d.module == "mod_b"}
    model_x.write_text(model_x.read_text().replace("title = fields.Char()", "pass"))
    after = {d.rule for d in _same(root, reuse) if d.module == "mod_b"}
    assert after != before


def test_unchanged_project_is_not_scanned_again(tmp_path: Path, monkeypatch):
    root = tmp_path.resolve()
    _project(root)
    reuse = ScanReuse()
    _scan(root, reuse)
    from odoo_doctor.core import scanner

    def boom(*a, **k):
        raise AssertionError("graph rebuilt")

    monkeypatch.setattr(scanner, "build_project_graph", boom)
    _scan(root, reuse)


def test_only_changed_files_run_the_file_rules(tmp_path: Path, monkeypatch):
    root = tmp_path.resolve()
    _project(root)
    reuse = ScanReuse()
    _scan(root, reuse)
    seen: list[str] = []
    from odoo_doctor.rules.registry import default_registry

    meta, func = default_registry.get("eval-usage")

    def spy(path, *a):
        seen.append(Path(path).parent.parent.name)
        return func(path, *a)

    monkeypatch.setattr(
        default_registry,
        "_rules",
        [(m, spy if m is meta else f) for m, f in default_registry._rules],
    )
    monkeypatch.setattr(spy, "__module__", func.__module__, raising=False)
    target = root / "mod_c" / "models" / "m.py"
    target.write_text(target.read_text() + "\n# x\n")
    time.sleep(0.01)
    _scan(root, reuse)
    assert set(seen) == {"mod_c"}


def test_config_change_drops_what_was_kept(tmp_path: Path):
    root = tmp_path.resolve()
    _project(root)
    reuse = ScanReuse()
    assert any(d.rule == "raw-sql-string-interpolation" for d in _scan(root, reuse)[0])
    toml = root / "odoo-doctor.toml"
    toml.write_text(
        toml.read_text() + '\n[ignore]\nrules = ["raw-sql-string-interpolation"]\n'
    )
    assert not any(d.rule == "raw-sql-string-interpolation" for d in _same(root, reuse))


def test_stamper_sees_a_rewrite_with_the_same_size_and_mtime(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("aaaa")
    first = Stamper({})
    sig = first.file(f)
    assert str(f) in first.racy  # just written: its content is recorded
    mtime = f.stat().st_mtime_ns
    f.write_text("bbbb")  # same size...
    import os

    os.utime(f, ns=(mtime, mtime))  # ...and the same mtime
    assert Stamper(first.racy).file(f) != sig
    assert Stamper(first.racy).file(f) == Stamper(first.racy).file(f)
