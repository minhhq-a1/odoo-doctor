# src/odoo_doctor/graph/source_index.py
"""Build an index of models and XML IDs from Odoo source path."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from odoo_doctor.parsers.python_models import parse_models


@dataclass(frozen=True)
class SourceIndex:
    model_owners: dict[str, str]  # model_name -> owning module name
    xml_id_owners: dict[str, str]  # xml_id -> owning module name


def build_source_index(source_path: Path | str | None) -> SourceIndex:
    """Scan and index all addons in the Odoo source path."""
    model_owners: dict[str, str] = {}
    xml_id_owners: dict[str, str] = {}

    if not source_path:
        return SourceIndex(model_owners, xml_id_owners)

    p = Path(source_path).resolve()
    if not p.is_dir():
        return SourceIndex(model_owners, xml_id_owners)

    # Odoo standard addon locations, plus direct addons roots for custom layouts.
    scan_dirs = [p / "addons", p / "odoo" / "addons"]
    if not (p / "__manifest__.py").exists():
        scan_dirs.append(p)
    addon_dirs: list[Path] = []

    for d in scan_dirs:
        if d.is_dir():
            for child in d.iterdir():
                if child.is_dir() and (child / "__manifest__.py").exists():
                    addon_dirs.append(child)

    # Index discovered addons
    for addon_dir in addon_dirs:
        module_name = addon_dir.name
        manifest_file = addon_dir / "__manifest__.py"

        try:
            _manifest = ast.literal_eval(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(_manifest, dict):
            continue

        # 1. Parse models
        for py_file in addon_dir.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            try:
                for m in parse_models(py_file):
                    if m.name:
                        model_owners[m.name] = module_name
            except (OSError, UnicodeDecodeError):
                # Best-effort scanning: tolerate unreadable or non-UTF-8 files in configured source path
                pass

        # 2. XML ID indexing is deferred for odoo_source_path (model-only in spec v3)
        pass

    return SourceIndex(model_owners, xml_id_owners)
