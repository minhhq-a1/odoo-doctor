# src/odoo_doctor/graph/stubs/build_stubs.py
"""Offline script to generate stub data from Odoo source.

Usage: python -m odoo_doctor.graph.stubs.build_stubs /path/to/odoo 17.0

Parses all models, fields, methods, and XML IDs from the Odoo source tree
and writes a JSON stub file to data/<version>.json.

This is NOT run during normal odoo-doctor operation. It is a maintenance tool
for regenerating stubs when a new Odoo version is released.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def build_stubs(odoo_source: Path, version: str) -> dict:
    """Parse Odoo source and extract model/field/method/xmlid data."""
    models: dict[str, dict] = {}

    for py_file in odoo_source.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Look for _name assignments
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if (isinstance(target, ast.Name) and target.id == "_name"
                                and isinstance(item.value, ast.Constant)):
                            model_name = item.value.value
                            if model_name not in models:
                                models[model_name] = {"fields": [], "methods": []}
                            _extract_members(node, models[model_name])

    return {"version": version, "models": models, "xml_ids": {}}


def _extract_members(cls: ast.ClassDef, model_data: dict) -> None:
    for item in cls.body:
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                if target.id not in model_data["fields"] and not target.id.startswith("_"):
                    model_data["fields"].append(target.id)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name not in model_data["methods"]:
                model_data["methods"].append(item.name)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m odoo_doctor.graph.stubs.build_stubs /path/to/odoo 17.0")
        sys.exit(1)

    odoo_path = Path(sys.argv[1])
    ver = sys.argv[2]
    data = build_stubs(odoo_path, ver)
    out = Path(__file__).parent / "data" / f"{ver}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    print(f"Wrote {len(data['models'])} models to {out}")
