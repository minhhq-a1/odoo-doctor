# src/odoo_doctor/discovery/addons.py
"""Discover Odoo addons by scanning for __manifest__.py."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from odoo_doctor.core.source import read_source



@dataclass
class AddonInfo:
    name: str
    path: Path
    manifest: dict


def discover_addons(
    addons_paths: list[Path],
    target_modules: list[str] | None = None,
) -> list[AddonInfo]:
    """Find all installable addons under the given paths."""
    found: list[AddonInfo] = []

    for base in addons_paths:
        if not base.is_dir():
            continue
        # Check if base itself is an addon
        manifest_file = base / "__manifest__.py"
        if manifest_file.exists():
            _try_add(base, manifest_file, target_modules, found)
            continue
        # Otherwise scan children
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            mf = child / "__manifest__.py"
            if mf.exists():
                _try_add(child, mf, target_modules, found)

    return found


def _try_add(
    addon_dir: Path,
    manifest_file: Path,
    target_modules: list[str] | None,
    out: list[AddonInfo],
) -> None:
    source = read_source(manifest_file)
    if source is None:
        return
    try:
        manifest = ast.literal_eval(source)
    except (SyntaxError, ValueError, RecursionError):
        return

    if not isinstance(manifest, dict):
        return
    if not manifest.get("installable", True):
        return

    name = addon_dir.name
    if target_modules and name not in target_modules:
        return

    out.append(AddonInfo(name=name, path=addon_dir, manifest=manifest))
