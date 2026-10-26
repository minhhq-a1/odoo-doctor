"""removed-core-xml-id: core ids that an older Odoo declared and the target does not."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from odoo_doctor.graph import core_index
from odoo_doctor.rules.upgrade_safety.removed_core_xml_id import (
    check_removed_core_xml_id,
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
            "base": {"xml_ids": ["old_group", "kept"]},
            "gone": {"xml_ids": ["g"]},
        },
    )
    _put(d, "19.0", {"base": {"xml_ids": ["kept"]}})
    yield
    core_index._cached.cache_clear()


def _record(ref: str, extra: str = "") -> str:
    return (
        f'<odoo><record id="r" model="res.partner">\n'
        f'<field name="parent_id" ref="{ref}"/>\n{extra}</record></odoo>'
    )


def _diags(tmp_path: Path, files: dict[str, str], version: str = "19.0"):
    return check_removed_core_xml_id(module_ctx(tmp_path / "proj", files, version))


def test_removed_id_in_a_record(tmp_path: Path, indexes):
    (d,) = _diags(tmp_path, {"d.xml": _record("base.old_group")})
    assert (d.rule, d.confidence, d.line, d.tier) == (
        "removed-core-xml-id",
        "high",
        2,
        "P1",
    )
    assert d.title == "Core XML id removed: base.old_group"


def test_removed_inherit_id(tmp_path: Path, indexes):
    xml = (
        '<odoo><record id="v" model="ir.ui.view">'
        '<field name="inherit_id" ref="base.old_group"/>'
        '<field name="model">res.partner</field>'
        '<field name="arch" type="xml"><form/></field></record></odoo>'
    )
    (d,) = _diags(tmp_path, {"v.xml": xml})
    assert d.title == "Core XML id removed: base.old_group"


def test_removed_module_is_medium(tmp_path: Path, indexes):
    (d,) = _diags(tmp_path, {"d.xml": _record("gone.g")})
    assert d.confidence == "medium"


def test_python_env_ref(tmp_path: Path, indexes):
    py = (
        "def f(self):\n"
        "    a = self.env.ref('base.old_group')\n"
        "    b = self.env.ref('base.old_group', raise_if_not_found=False)\n"
        "    try:\n"
        "        c = self.env.ref('base.old_group')\n"
        "    except ValueError:\n"
        "        c = self.env.ref('base.old_group')\n"
        "    d = self.env.ref(name)\n"
    )
    diags = _diags(tmp_path, {"m.py": py})
    assert [(d.line, d.confidence) for d in diags] == [
        (2, "high"),
        (5, "medium"),
        (7, "high"),
    ]


@pytest.mark.parametrize(
    "ref",
    [
        "base.kept",  # still declared
        "base.never_seen",  # in no version
        "unknown.x",  # not a core module we know
        "base.module_sale",  # created at runtime
        "base.model_res_partner",
        "base.field_res_partner__name",
        "old_group",  # no module part: local
        "mod.old_group",  # own module
    ],
)
def test_silent_cases(tmp_path: Path, indexes, ref: str):
    assert _diags(tmp_path, {"d.xml": _record(ref)}) == []


def test_silent_without_a_gap_or_an_index(tmp_path: Path, indexes):
    files = {"d.xml": _record("base.old_group")}
    assert _diags(tmp_path, files, "17.0") == []
    assert _diags(tmp_path / "other", files, "20.0") == []


def test_id_declared_by_the_scan_in_the_core_namespace(tmp_path: Path, indexes):
    files = {
        "d.xml": _record("base.old_group"),
        "e.xml": '<odoo><record id="base.old_group" model="res.groups"/></odoo>',
    }
    assert _diags(tmp_path, files) == []
