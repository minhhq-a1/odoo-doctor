# src/odoo_doctor/graph/core_index/__init__.py
"""Packaged index of Odoo community core: files under ``static/`` and XML ids per module.

One gzip JSON per Odoo version (``data/<version>.json.gz``, built by ``build.py``). A rule
that finds a reference to a core module outside the scan asks "does it exist in the
target version, and did it exist in an older one?": a reference that existed before and is
gone now is a real break, while one never seen anywhere is silent (it may belong to
enterprise, OCA, or be created at runtime). See ``docs/core-index.md``.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path

FORMAT = 1
_DATA_DIR = Path(__file__).parent / "data"


class CoreIndex:
    """The modules of one Odoo version, with lazily built per-module lookup sets."""

    def __init__(self, version: str, modules: Mapping[str, Mapping]) -> None:
        self.version = version
        self._modules = modules
        self._static: dict[str, frozenset[str]] = {}
        self._xml_ids: dict[str, frozenset[str]] = {}
        self._basenames: dict[str, list[tuple[str, str]]] | None = None

    def has_module(self, module: str) -> bool:
        return module in self._modules

    def has_static(self, module: str, rel_path: str) -> bool:
        """``rel_path`` is relative to the module root, e.g. ``static/src/core/x.js``."""
        if module not in self._static:
            self._static[module] = frozenset(
                self._modules.get(module, {}).get("static", ())
            )
        return rel_path in self._static[module]

    def has_xml_id(self, module: str, name: str) -> bool:
        """``name`` is the id without its module prefix."""
        if module not in self._xml_ids:
            self._xml_ids[module] = frozenset(
                self._modules.get(module, {}).get("xml_ids", ())
            )
        return name in self._xml_ids[module]

    def static_by_basename(self, basename: str) -> list[tuple[str, str]]:
        """``(module, rel_path)`` of every static file with this basename (built on demand)."""
        if self._basenames is None:
            index: dict[str, list[tuple[str, str]]] = {}
            for module, entry in self._modules.items():
                for rel in entry.get("static", ()):
                    index.setdefault(rel.rpartition("/")[2], []).append((module, rel))
            self._basenames = index
        return self._basenames.get(basename, [])


def _major(version: str) -> int | None:
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def _load(version: str, data_dir: Path) -> CoreIndex | None:
    try:
        with gzip.open(data_dir / f"{version}.json.gz", "rt", encoding="utf-8") as f:
            raw = json.load(f)
        if raw.get("format") != FORMAT or not isinstance(raw.get("modules"), dict):
            return None
        return CoreIndex(str(raw.get("version", version)), raw["modules"])
    except (OSError, ValueError, EOFError):  # missing, corrupt gzip or JSON: no index
        return None


@cache
def _cached(version: str, data_dir: Path) -> CoreIndex | None:
    return _load(version, data_dir)


def get_core_index(version: str) -> CoreIndex | None:
    """The packaged index for ``version`` (``"19.0"``; a longer form uses its major), or None."""
    major = _major(version)
    return None if major is None else _cached(f"{major}.0", _DATA_DIR)


def older_indexes(version: str) -> list[CoreIndex]:
    """Packaged indexes of the majors below ``version``'s, oldest first."""
    major = _major(version)
    if major is None:
        return []
    majors = sorted(
        m
        for p in _DATA_DIR.glob("*.0.json.gz")
        if (m := _major(p.name)) is not None and m < major
    )
    found = (_cached(f"{m}.0", _DATA_DIR) for m in majors)
    return [i for i in found if i is not None]
