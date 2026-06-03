# src/odoo_doctor/parsers/manifest.py
"""Parse __manifest__.py safely using ast.literal_eval."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ManifestData:
    name: str
    version: str | None = None
    depends: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    license: str | None = None
    installable: bool = True
    raw: dict = field(default_factory=dict)


def parse_manifest(addon_path: Path) -> ManifestData | None:
    """Parse __manifest__.py from an addon directory. Returns None if missing/invalid."""
    manifest_file = addon_path / "__manifest__.py"
    if not manifest_file.exists():
        return None

    try:
        raw = ast.literal_eval(manifest_file.read_text())
    except (SyntaxError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None

    return ManifestData(
        name=raw.get("name", addon_path.name),
        version=raw.get("version"),
        depends=raw.get("depends", []),
        data=raw.get("data", []),
        license=raw.get("license"),
        installable=raw.get("installable", True),
        raw=raw,
    )
