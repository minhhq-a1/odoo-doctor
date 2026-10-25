"""Core index: deterministic builder, loader, lookups."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from odoo_doctor.graph import core_index
from odoo_doctor.graph.core_index import CoreIndex, get_core_index, older_indexes
from odoo_doctor.graph.core_index.build import build_core_index, write_core_index


def _tree(root: Path) -> Path:
    web = root / "addons" / "web"
    (web / "static/src/core").mkdir(parents=True)
    (web / "static/src/core/hooks.js").write_text("")
    (web / "static/src/tpl.xml").write_text("<templates/>")
    (web / "static/src/logo.png").write_bytes(b"x")
    (web / "static/tests").mkdir(parents=True)
    (web / "static/tests/helpers.js").write_text("")
    (web / "static/lib").mkdir()
    (web / "static/lib/big.js").write_text("")
    (web / "views").mkdir()
    (web / "views/v.xml").write_text(
        '<odoo><record id="layout" model="ir.ui.view"/>'
        '<template id="frontend"/><menuitem id="menu_root"/>'
        '<record id="base.shared" model="x"/>'
        '<record id="model_hidden" model="x"/></odoo>'
    )
    (web / "security").mkdir()
    (web / "security/ir.model.access.csv").write_text(
        "id,name\naccess_a,a\nother.access_b,b\n"
    )
    (web / "bad.xml").write_bytes(b"\xff\xfe\x00")
    (web / "__manifest__.py").write_text(
        "{'name': 'web', 'data': ['views/v.xml', 'security/ir.model.access.csv', 'bad.xml']}"
    )
    (web / "__init__.py").write_text("")
    return root


def test_build_collects_static_and_ids(tmp_path: Path):
    data = build_core_index(_tree(tmp_path), "19.0")
    assert data["format"] == 1 and data["version"] == "19.0"
    web = data["modules"]["web"]
    assert web["static"] == [
        "static/src/core/hooks.js",
        "static/src/tpl.xml",
        "static/tests/helpers.js",
    ]
    assert web["xml_ids"] == ["access_a", "frontend", "layout", "menu_root"]
    # an id declared in another module's namespace belongs to that namespace
    assert data["modules"]["base"]["xml_ids"] == ["shared"]
    assert data["modules"]["other"]["xml_ids"] == ["access_b"]


def test_skip_ids_of_keeps_the_module(tmp_path: Path):
    data = build_core_index(_tree(tmp_path), "19.0", skip_ids_of="web")
    assert data["modules"]["web"]["xml_ids"] == []
    assert data["modules"]["web"]["static"]


def test_write_is_byte_identical(tmp_path: Path):
    data = build_core_index(_tree(tmp_path), "19.0")
    a = write_core_index(data, tmp_path / "a").read_bytes()
    b = write_core_index(data, tmp_path / "b").read_bytes()
    assert a == b


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(core_index, "_DATA_DIR", d)
    core_index._cached.cache_clear()
    yield d
    core_index._cached.cache_clear()


def _put(d: Path, version: str, modules: dict, fmt: int = 1) -> None:
    payload = {"format": fmt, "version": version, "modules": modules}
    with gzip.open(d / f"{version}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f)


def test_loader_lookups(data_dir: Path):
    _put(data_dir, "19.0", {"web": {"static": ["static/src/a.js"], "xml_ids": ["x"]}})
    idx = get_core_index("19.0.1.0")  # a longer form resolves by major
    assert idx is not None and idx.has_module("web") and not idx.has_module("mail")
    assert idx.has_static("web", "static/src/a.js")
    assert not idx.has_static("web", "static/src/b.js")
    assert idx.has_xml_id("web", "x") and not idx.has_xml_id("web", "y")
    assert idx.static_by_basename("a.js") == [("web", "static/src/a.js")]
    assert idx.static_by_basename("zzz.js") == []


def test_loader_failures_are_silent(data_dir: Path):
    assert get_core_index("19.0") is None  # missing
    (data_dir / "18.0.json.gz").write_bytes(b"not gzip")
    assert get_core_index("18.0") is None
    _put(data_dir, "17.0", {}, fmt=2)
    assert get_core_index("17.0") is None
    assert get_core_index("unknown") is None


def test_older_indexes_oldest_first(data_dir: Path):
    for v in ("19.0", "17.0", "18.0"):
        _put(data_dir, v, {})
    assert [i.version for i in older_indexes("19.0")] == ["17.0", "18.0"]
    assert [i.version for i in older_indexes("18.0")] == ["17.0"]
    assert older_indexes("17.0") == [] and older_indexes("x") == []


def test_unknown_keys_and_modules_are_ignored():
    idx = CoreIndex("19.0", {"web": {"static": [], "xml_ids": [], "new_key": [1]}})
    assert not idx.has_static("nope", "a") and not idx.has_xml_id("nope", "a")
