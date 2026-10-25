"""removed-core-js-import: core JS that an older Odoo had and the target lacks."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from odoo_doctor.graph import core_index
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.suppression import scan_js_suppressions
from odoo_doctor.rules.upgrade_safety.removed_core_js_import import (
    check_removed_core_js_import,
)

from ._module import module_ctx


def _put(d: Path, version: str, modules: dict) -> None:
    data = {"format": 1, "version": version, "modules": modules}
    with gzip.open(d / f"{version}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def indexes(tmp_path: Path, monkeypatch):
    d = tmp_path / "idx"
    d.mkdir()
    monkeypatch.setattr(core_index, "_DATA_DIR", d)
    core_index._cached.cache_clear()
    _put(
        d,
        "17.0",
        {
            "web": {"static": ["static/src/legacy/old.js", "static/src/core/kept.js"]},
            "gone": {"static": ["static/src/g.js"]},
        },
    )
    _put(
        d,
        "19.0",
        {"web": {"static": ["static/src/core/kept.js", "static/src/new/old.js"]}},
    )
    yield d
    core_index._cached.cache_clear()


def _diags(tmp_path: Path, js: str, version: str = "19.0"):
    ctx = module_ctx(tmp_path / "proj", {"static/src/a.js": js}, version)
    return check_removed_core_js_import(ctx)


def test_removed_file_is_high_with_relocation_hint(tmp_path: Path, indexes):
    (d,) = _diags(tmp_path, 'import { x } from "@web/legacy/old";\n')
    assert (d.rule, d.confidence, d.line, d.tier, d.category) == (
        "removed-core-js-import",
        "high",
        1,
        "P1",
        "Upgrade Safety",
    )
    assert d.title == "Core JS module removed: @web/legacy/old"
    assert "17.0" in d.message and "19.0" in d.message
    assert "web/static/src/new/old.js" in d.help


def test_removed_module_is_medium(tmp_path: Path, indexes):
    (d,) = _diags(tmp_path, 'import "@gone/g";\n')
    assert d.confidence == "medium" and d.title == "Core JS module removed: @gone/g"


def test_dynamic_import_is_at_most_medium(tmp_path: Path, indexes):
    (d,) = _diags(tmp_path, 'const m = await import("@web/legacy/old");\n')
    assert d.confidence == "medium"


@pytest.mark.parametrize(
    "js",
    [
        'import { a } from "@web/core/kept";',  # still there
        'import { a } from "@web/never/seen";',  # in no version: silent
        'import { a } from "@unknown/x";',  # not a core module we know
        'import { owl } from "@odoo/owl";',
        'import { a } from "./local";',
        '// import { a } from "@web/legacy/old";',
    ],
)
def test_silent_cases(tmp_path: Path, indexes, js: str):
    assert _diags(tmp_path, js + "\n") == []


def test_silent_without_a_gap_or_an_index(tmp_path: Path, indexes):
    js = 'import { x } from "@web/legacy/old";\n'
    assert _diags(tmp_path, js, "17.0") == []  # nothing older than 17 is packaged
    assert _diags(tmp_path, js, "20.0") == []  # no index for 20


def test_scanned_module_is_not_core(tmp_path: Path, indexes):
    root = tmp_path / "proj"
    module_ctx(root, {"static/src/a.js": 'import "@web/legacy/old";\n'})
    web = root / "web"
    web.mkdir()
    (web / "__manifest__.py").write_text("{'name': 'web', 'version': '19.0.1.0.0'}")
    (web / "__init__.py").write_text("")
    ctx = build_project_graph([root], odoo_version="19.0").modules["mod"]
    assert check_removed_core_js_import(ctx) == []


def test_missing_index_files_are_silent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core_index, "_DATA_DIR", tmp_path / "none")
    core_index._cached.cache_clear()
    assert _diags(tmp_path, 'import "@web/legacy/old";\n') == []


def test_js_suppression_comment(tmp_path: Path):
    js = tmp_path / "a.js"
    js.write_text(
        "// odoo-doctor: disable=removed-core-js-import\n"
        'import "@web/legacy/old";\n'
        "// odoo-doctor: disable-file=other-rule\n"
    )
    assert scan_js_suppressions(js) == {
        (str(js), 2, "removed-core-js-import"),
        (str(js), 0, "other-rule"),
    }


def test_scan_end_to_end_suppression_and_cache(tmp_path: Path, indexes):
    from odoo_doctor.core.cache import ScanCache
    from odoo_doctor.core.config import OdooDoctorConfig
    from odoo_doctor.core.scanner import collect_scores

    root = tmp_path / "proj"
    module_ctx(root, {"static/src/a.js": 'import "@web/legacy/old";\n'})
    js = root / "mod" / "static" / "src" / "a.js"
    cfg = OdooDoctorConfig(odoo_version="19.0")
    cache = ScanCache(tmp_path / ".cache")

    def run():
        diags, _ = collect_scores(
            addon_paths=[root],
            cfg=cfg,
            version="19.0",
            config_root=root,
            cache=cache,
            force_version=True,
        )
        return [d.rule for d in diags if d.rule == "removed-core-js-import"]

    assert run() == ["removed-core-js-import"]
    assert run() == ["removed-core-js-import"]  # cache hit, same result
    js.write_text(
        "// odoo-doctor: disable=removed-core-js-import\n"
        'import "@web/legacy/old";\n'
    )
    assert run() == []  # the edit is seen (cache) and the comment suppresses it
