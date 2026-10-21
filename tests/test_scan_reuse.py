"""A scan that reuses the previous one (the language server's) equals a scan from scratch."""

from __future__ import annotations

import dataclasses
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import pytest

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


def _project(root: Path, ruff: bool = False, extra: str = "") -> None:
    (root / "odoo-doctor.toml").write_text(
        '[odoo-doctor]\nodoo_version = "17.0"\n' + extra + "\n"
        f"[adapters]\nruff = {str(ruff).lower()}\npylint_odoo = false\n"
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


# --- the safeguards through collect_scores, not the Stamper alone ---------------

posix = pytest.mark.skipif(
    sys.platform == "win32", reason="utime/ctime/inode semantics"
)
EVAL = "from odoo import models\n\nclass E(models.Model):\n    _name = 'x.e'\n    def f(self, n):\n        {call}(n)\n"


def _eval_project(tmp_path: Path):
    root = tmp_path.resolve()
    _project(root)
    f = root / "mod_c" / "models" / "e.py"
    f.write_text(EVAL.format(call="evax"))
    return root, f


def _has_eval(diags) -> bool:
    return any(d.rule == "eval-usage" for d in diags)


def test_racy_files_are_remembered_after_a_changed_scan(tmp_path: Path):
    root, f = _eval_project(tmp_path)
    reuse = ScanReuse()
    _scan(root, reuse)
    f.write_text(EVAL.format(call="evax") + "# x\n")  # a changed scan
    _scan(root, reuse)
    assert str(f) in reuse.racy


@posix
def test_same_size_rewrite_with_the_old_mtime_is_seen(tmp_path: Path):
    root, f = _eval_project(tmp_path)
    reuse = ScanReuse()
    _scan(root, reuse)
    f.write_text(EVAL.format(call="evax") + "# x\n")
    _scan(root, reuse)
    st = f.stat()
    f.write_text(EVAL.format(call="eval") + "# x\n")  # same size
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))  # and the old mtime
    assert _has_eval(_same(root, reuse))
    time.sleep(2.1)  # outside the racy window
    f.write_text(EVAL.format(call="evax") + "# x\n")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert not _has_eval(_same(root, reuse))


@posix
def test_a_save_by_rename_is_seen(tmp_path: Path):
    root, f = _eval_project(tmp_path)
    reuse = ScanReuse()
    _scan(root, reuse)
    st = f.stat()
    tmp = f.with_name("e.tmp")
    tmp.write_text(EVAL.format(call="eval"))  # same size
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(tmp, f)
    assert _has_eval(_same(root, reuse))


def test_same_size_edit_with_a_later_mtime_is_seen(tmp_path: Path):
    root, f = _eval_project(tmp_path)
    old = 1_000_000_000_000_000_000  # long ago: outside the racy window
    os.utime(f, ns=(old, old))
    reuse = ScanReuse()
    _scan(root, reuse)
    f.write_text(EVAL.format(call="eval"))
    os.utime(f, ns=(old + 5_000_000_000, old + 5_000_000_000))
    assert _has_eval(_same(root, reuse))


# --- linters, source index and plugins in the keys ------------------------------

FAKE_RUFF = r"""#!/bin/sh
if [ "$1" = "--version" ]; then echo "ruff 0.16.0"; exit 0; fi
out=""
for t in "$@"; do
  case "$t" in /*)
    if [ "$(basename "$t")" = "mod_b" ] && grep -q BAD "$t/../base_x/models/m.py" 2>/dev/null; then
      out="$out{\"code\":\"F841\",\"filename\":\"$t/models/m.py\",\"location\":{\"row\":1,\"column\":1},\"message\":\"sibling\"},"
    fi
    for f in $(grep -rl BAD --include=*.py "$t" 2>/dev/null); do
      out="$out{\"code\":\"F841\",\"filename\":\"$f\",\"location\":{\"row\":1,\"column\":1},\"message\":\"own\"},"
    done;;
  esac
done
echo "[${out%,}]"
"""


@posix
def test_linter_results_follow_edits_in_the_addon_and_its_dependencies(
    tmp_path: Path, monkeypatch
):
    from odoo_doctor.core import cache as cache_mod

    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "ruff"
    exe.write_text(FAKE_RUFF)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(cache_mod, "_tool_versions", {})
    root = tmp_path / "proj"
    root.mkdir()
    _project(root, ruff=True)
    reuse = ScanReuse()

    def ruff(diags):
        return sorted((d.module, d.message) for d in diags if d.source == "ruff")

    assert ruff(_same(root, reuse)) == []
    own = root / "mod_c" / "models" / "m.py"
    own.write_text(own.read_text() + "# BAD\\n")
    assert ruff(_same(root, reuse)) == [("mod_c", "own")]
    dep = root / "base_x" / "models" / "m.py"  # mod_b depends on base_x
    dep.write_text(dep.read_text() + "# BAD\\n")
    assert ("mod_b", "sibling") in ruff(_same(root, reuse))
    dep.write_text(dep.read_text().replace("BAD", "ok "))
    assert ("mod_b", "sibling") not in ruff(_same(root, reuse))


def test_source_index_follows_edits_in_the_odoo_source(tmp_path: Path):
    core = tmp_path / "core" / "addons" / "fakecore"
    (core / "models").mkdir(parents=True)
    (core / "__manifest__.py").write_text('{"name": "fakecore", "depends": []}')
    model = core / "models" / "m.py"
    model.write_text(
        "from odoo import models\n\nclass F(models.Model):\n    _name = 'fake.model'\n"
    )
    root = tmp_path / "proj"
    root.mkdir()
    _project(root, extra=f'odoo_source_path = "{(tmp_path / "core").as_posix()}"')
    _module(root, "mod_s", ["base"], "x.s")
    (root / "mod_s" / "models" / "m.py").write_text(
        "from odoo import models\n\nclass S(models.Model):\n    _inherit = 'fake.model'\n"
    )
    reuse = ScanReuse()

    def missing(diags):
        return [d for d in diags if d.rule == "manifest-missing-dependency"]

    assert missing(_same(root, reuse))  # owner found in the source
    model.write_text(model.read_text().replace("fake.model", "fake.modez"))  # same size
    os.utime(model, ns=(1_000_000_000_000_000_000,) * 2)
    assert not missing(_same(root, reuse))
    model.write_text(model.read_text().replace("fake.modez", "fake.model"))
    assert missing(_same(root, reuse))


class _PluginRule:
    """A rule registered the way a plugin does (its module is not odoo_doctor's)."""

    def __init__(self, needs_context: bool) -> None:
        self.calls = 0
        self.needs_context = needs_context

    def __enter__(self):
        from odoo_doctor.rules.registry import RuleMeta, default_registry

        def func(*args):
            self.calls += 1
            return []

        func.__module__ = "fake_plugin"
        meta = RuleMeta(
            "fake-plugin-rule",
            "Security",
            "P3",
            "info",
            "low",
            self.needs_context,
            None,
        )
        default_registry.register(meta, func)
        return self

    def __exit__(self, *exc):
        from odoo_doctor.rules.registry import default_registry

        default_registry.unregister("fake-plugin-rule")


@pytest.mark.parametrize("needs_context", [True, False])
def test_a_plugin_rule_runs_on_every_scan(tmp_path: Path, needs_context: bool):
    root = tmp_path.resolve()
    _project(root)
    with _PluginRule(needs_context) as plugin:
        reuse = ScanReuse()
        _scan(root, reuse)
        first = plugin.calls
        assert first > 0
        _scan(root, reuse)  # nothing changed
        assert plugin.calls == 2 * first


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


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_ruff_configuration_and_ignore_files_do_not_change_a_reusing_scan(
    tmp_path: Path,
):
    """The repo's ruff.toml, the file it extends and .gitignore are not ruff inputs (ruff runs
    --isolated --no-respect-gitignore): editing them keeps the findings, and a reusing scan
    still equals one from scratch."""
    root = tmp_path.resolve()
    _project(root, ruff=True)
    m = root / "mod_c" / "models" / "m.py"
    m.write_text("import os\n" + m.read_text())  # F401 with ruff's defaults

    def f401(diags):
        return [d for d in diags if d.rule == "F401"]

    reuse = ScanReuse()
    assert f401(_same(root, reuse))
    config = root / "ruff.toml"
    config.write_text('[lint]\nignore = ["F401"]\n')
    assert f401(_same(root, reuse))
    (root / "shared.toml").write_text('[lint]\nignore = ["F401"]\n')
    config.write_text('extend = "shared.toml"\n')
    assert f401(_same(root, reuse))
    (root / ".gitignore").write_text("mod_c/models/m.py\n")
    assert f401(_same(root, reuse))
