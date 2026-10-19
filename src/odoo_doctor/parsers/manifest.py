# src/odoo_doctor/parsers/manifest.py
"""Parse __manifest__.py safely using ast.literal_eval."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from odoo_doctor.core.source import chain_too_long, read_source


@dataclass
class ManifestData:
    name: str
    version: str | None = None
    depends: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    license: str | None = None
    installable: bool = True
    assets: dict[str, list[str]] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def _str_list(value: object) -> list[str]:
    """A manifest list of strings; anything else (None, 5, nested lists) is dropped."""
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in value if isinstance(v, str)]


def _external_dependencies(value: object) -> dict[str, list[str]]:
    """`external_dependencies` as {kind: [package, ...]}; a malformed value yields {}."""
    if not isinstance(value, dict):
        return {}
    return {k: _str_list(v) for k, v in value.items() if isinstance(k, str)}


def parse_manifest(addon_path: Path) -> ManifestData | None:
    """Parse __manifest__.py from an addon directory. Returns None if missing/invalid."""
    manifest_file = addon_path / "__manifest__.py"
    if not manifest_file.exists():
        return None

    source = read_source(manifest_file)
    if source is None:
        return None
    if chain_too_long(source):
        return None
    try:
        raw = ast.literal_eval(source)
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return None

    if not isinstance(raw, dict):
        return None

    assets = raw.get("assets", {})
    if not isinstance(assets, dict):
        assets = {}

    version = raw.get("version")
    if "external_dependencies" in raw:
        raw = {
            **raw,
            "external_dependencies": _external_dependencies(
                raw["external_dependencies"]
            ),
        }

    return ManifestData(
        name=raw.get("name", addon_path.name),
        version=version if isinstance(version, str) else None,
        depends=_str_list(raw.get("depends")),
        data=_str_list(raw.get("data")),
        license=raw.get("license"),
        installable=raw.get("installable", True),
        assets=assets,
        raw=raw,
    )
