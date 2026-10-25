# src/odoo_doctor/graph/core_index/build.py
"""Build ``data/<version>.json.gz`` from an Odoo source checkout (run by hand, like build_stubs).

    python -m odoo_doctor.graph.core_index.build \\
        --odoo-path /path/to/odoo --version 19.0 [--skip-ids-of 'l10n_*']

The output holds identifiers only (paths and XML ids), never source code, and is byte-identical
for the same checkout (sorted keys, gzip ``mtime=0``).
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import gzip
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from odoo_doctor.core.git import run_git
from odoo_doctor.core.source import is_scannable, read_source
from odoo_doctor.graph.core_index import FORMAT
from odoo_doctor.graph.source_index import _addon_dirs
from odoo_doctor.parsers.manifest import parse_manifest
from odoo_doctor.parsers.xml_records import parse_xml_records

_STATIC_SUFFIXES = (".js", ".xml", ".scss", ".sass", ".css", ".less")
_STATIC_ROOTS = ("static/src", "static/tests")
# Created from the model/field/module registries at runtime, never declared in data files.
_DYNAMIC_PREFIXES = ("model_", "field_", "module_")


def _static_files(addon: Path) -> list[str]:
    found: list[str] = []
    for root in _STATIC_ROOTS:
        base = addon / root
        for dirpath, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {"node_modules", "__pycache__"}]
            for name in names:
                path = Path(dirpath, name)
                if name.endswith(_STATIC_SUFFIXES) and is_scannable(path, addon):
                    found.append(path.relative_to(addon).as_posix())
    return sorted(found)


def _csv_ids(path: Path, addon: Path) -> list[str]:
    text = read_source(path, addon)
    if not text:
        return []
    rows = csv.reader(io.StringIO(text))
    header = next(rows, None)
    if not header or header[0].strip() != "id":
        return []
    return [r[0].strip() for r in rows if r and r[0].strip()]


def _data_files(addon: Path, manifest) -> list[str]:
    names = list(manifest.data)
    demo = manifest.raw.get("demo", [])
    return names + [n for n in demo if isinstance(n, str)]


def build_core_index(odoo_path: Path, version: str, skip_ids_of: str = "") -> dict:
    """The index of the community addons under ``odoo_path`` (pure: returns the dict)."""
    modules: dict[str, dict[str, set[str]]] = {}
    patterns = [p for p in skip_ids_of.split(",") if p]

    def entry(name: str) -> dict[str, set[str]]:
        return modules.setdefault(name, {"static": set(), "xml_ids": set()})

    for addon in sorted(_addon_dirs(odoo_path)):
        manifest = parse_manifest(addon)
        if manifest is None:
            continue
        entry(addon.name)["static"].update(_static_files(addon))
        for rel in _data_files(addon, manifest):
            path = addon / rel
            if not is_scannable(path, addon):
                continue
            if path.suffix == ".xml":
                ids = [r.xml_id for r in parse_xml_records(path, addon.name)]
            elif path.suffix == ".csv":
                ids = [
                    i if "." in i else f"{addon.name}.{i}"
                    for i in _csv_ids(path, addon)
                ]
            else:
                continue
            for xml_id in ids:
                ns, _, name = xml_id.partition(".")
                if not name or name.startswith(_DYNAMIC_PREFIXES):
                    continue
                if any(fnmatch.fnmatch(ns, p) for p in patterns):
                    continue
                entry(ns)["xml_ids"].add(name)
    return {
        "format": FORMAT,
        "version": version,
        "source": _source_info(odoo_path),
        "modules": {
            m: {k: sorted(v) for k, v in e.items()} for m, e in sorted(modules.items())
        },
    }


def _source_info(odoo_path: Path) -> dict:
    try:
        result = run_git(["rev-parse", "HEAD"], odoo_path, timeout=10)
        commit = result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return {
        "commit": commit,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def write_core_index(data: dict, out_dir: Path) -> Path:
    """Write ``<version>.json.gz`` deterministically (same data, same bytes)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{data['version']}.json.gz"
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz,
    ):
        gz.write(payload)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--odoo-path", required=True, type=Path)
    ap.add_argument("--version", required=True, help='e.g. "19.0"')
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    ap.add_argument(
        "--skip-ids-of",
        default="",
        help="comma separated module globs whose XML ids are left out (e.g. 'l10n_*')",
    )
    args = ap.parse_args(argv)
    data = build_core_index(args.odoo_path, args.version, args.skip_ids_of)
    path = write_core_index(data, args.out)
    print(f"{path} ({path.stat().st_size} bytes, {len(data['modules'])} modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
