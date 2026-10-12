# src/odoo_doctor/discovery/addons.py
"""Discover Odoo addons by scanning for __manifest__.py."""

from __future__ import annotations

import ast
import os
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


# Folders a hint never descends into: dependencies and tooling, not project addons.
_SKIPPED_DIRS = frozenset(
    {"node_modules", "__pycache__", "venv", "env", "site-packages", "build", "dist"}
)
_NESTED_MAX_DEPTH = 4  # base/<a>/<b>/<c>/<addon>
_NESTED_MAX_DIRS = 5000  # bounds the walk on a huge workspace


def find_nested_addon_roots(base: Path) -> list[tuple[Path, int]]:
    """Folders below ``base`` whose children are addons, with their addon count.

    Only used to hint where the addons are when ``base`` itself holds none; the scan
    never descends on its own. Hidden folders and dependency folders are skipped, an
    addon is not entered, and the walk is bounded in depth and in folders visited.
    """
    roots: dict[Path, int] = {}
    budget = _NESTED_MAX_DIRS

    def walk(folder: Path, depth: int) -> None:
        nonlocal budget
        try:
            children = sorted(
                (e for e in os.scandir(folder) if e.is_dir(follow_symlinks=False)),
                key=lambda e: e.name,
            )
        except OSError:
            return
        for entry in children:
            if entry.name.startswith(".") or entry.name in _SKIPPED_DIRS:
                continue
            budget -= 1
            if budget < 0:
                return
            child = Path(entry.path)
            if (child / "__manifest__.py").exists():
                if depth > 1:  # depth 1 is a direct child, which the scan sees itself
                    roots[folder] = roots.get(folder, 0) + 1
            elif depth < _NESTED_MAX_DEPTH:
                walk(child, depth + 1)

    walk(base, 1)
    return sorted(roots.items())
