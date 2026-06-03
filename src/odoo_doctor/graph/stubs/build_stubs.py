# src/odoo_doctor/graph/stubs/build_stubs.py
"""Generate stub JSON from Odoo source tree or a live Odoo RPC instance.

=== Source mode (offline) ===
    python -m odoo_doctor.graph.stubs.build_stubs \\
        --odoo-path /path/to/odoo \\
        --version 17.0 \\
        [--output src/odoo_doctor/graph/stubs/data/17.0.json]

=== RPC mode (live instance) ===
    python -m odoo_doctor.graph.stubs.build_stubs \\
        --rpc-url http://localhost:8069 \\
        --rpc-db mydb \\
        --rpc-user admin \\
        --rpc-password admin \\
        --version 17.0

Both modes write to the same JSON schema consumed by load_stubs().
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Optional
from collections import defaultdict


# ─── AST extraction ────────────────────────────────────────────────────────

# Field types defined by Odoo (fields.Xxx = ...)
_ODOO_FIELD_CALLS = {
    "Char", "Text", "Html", "Integer", "Float", "Boolean", "Date", "Datetime",
    "Binary", "Selection", "Many2one", "One2many", "Many2many", "Reference",
    "Monetary", "Image", "Json", "Properties", "PropertiesDefinition",
    "Many2oneReference", "Command",
}

_SKIP_METHOD_PREFIXES = ("__",)
_SKIP_DIRS = {"test", "tests", "static", "migrations", "wizard", ".git"}


def _is_field_call(node: ast.Assign) -> bool:
    """Return True if RHS is fields.Xxx(...) or just Xxx(...) from imports."""
    val = node.value
    if not isinstance(val, ast.Call):
        return False
    func = val.func
    if isinstance(func, ast.Attribute):
        return func.attr in _ODOO_FIELD_CALLS
    if isinstance(func, ast.Name):
        return func.id in _ODOO_FIELD_CALLS
    return False


def _extract_class_data(cls: ast.ClassDef) -> tuple[str | None, list[str], list[str]]:
    """Extract (_name, fields, methods) from a class definition."""
    model_name: str | None = None
    inherits: list[str] = []
    fields: list[str] = []
    methods: list[str] = []

    for item in cls.body:
        # _name = "..."
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "_name" and isinstance(item.value, ast.Constant):
                    model_name = str(item.value.value)
                elif target.id == "_inherit":
                    val = item.value
                    if isinstance(val, ast.Constant):
                        inherits.append(str(val.value))
                    elif isinstance(val, (ast.List, ast.Tuple)):
                        for elt in val.elts:
                            if isinstance(elt, ast.Constant):
                                inherits.append(str(elt.value))
                elif _is_field_call(item) and not target.id.startswith("_"):
                    if target.id not in fields:
                        fields.append(target.id)

        # AnnAssign: my_field: fields.Char = ...
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            fname = item.target.id
            if not fname.startswith("_") and fname not in fields:
                if item.value and _is_field_call(
                    ast.Assign(targets=[item.target], value=item.value, lineno=0, col_offset=0)
                ):
                    fields.append(fname)

        # Methods
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = item.name
            if not any(name.startswith(p) for p in _SKIP_METHOD_PREFIXES):
                if name not in methods:
                    methods.append(name)

    return model_name, fields, methods


def _should_skip_dir(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def parse_odoo_source(odoo_path: Path) -> dict[str, dict]:
    """Walk Odoo source and extract all model definitions."""
    models: dict[str, dict] = {}
    # Track fields/methods contributed from _inherit classes so we can merge
    inherit_extras: dict[str, dict] = defaultdict(lambda: {"fields": [], "methods": []})

    py_files = [
        p for p in odoo_path.rglob("*.py")
        if not _should_skip_dir(p) and not p.name.startswith("test_")
    ]

    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            model_name, fields, methods = _extract_class_data(node)

            if model_name:
                # Primary definition
                if model_name not in models:
                    models[model_name] = {"fields": [], "methods": []}
                for f in fields:
                    if f not in models[model_name]["fields"]:
                        models[model_name]["fields"].append(f)
                for m in methods:
                    if m not in models[model_name]["methods"]:
                        models[model_name]["methods"].append(m)
            elif fields or methods:
                # Pure _inherit extension — find inherited names
                for inh in _get_inherits(node):
                    for f in fields:
                        if f not in inherit_extras[inh]["fields"]:
                            inherit_extras[inh]["fields"].append(f)
                    for m in methods:
                        if m not in inherit_extras[inh]["methods"]:
                            inherit_extras[inh]["methods"].append(m)

    # Merge inherit extras into primary model entries
    for inh_name, extras in inherit_extras.items():
        if inh_name in models:
            for f in extras["fields"]:
                if f not in models[inh_name]["fields"]:
                    models[inh_name]["fields"].append(f)
            for m in extras["methods"]:
                if m not in models[inh_name]["methods"]:
                    models[inh_name]["methods"].append(m)

    return models


def _get_inherits(cls: ast.ClassDef) -> list[str]:
    """Get _inherit values from a class."""
    names: list[str] = []
    for item in cls.body:
        if not isinstance(item, ast.Assign):
            continue
        for target in item.targets:
            if isinstance(target, ast.Name) and target.id == "_inherit":
                val = item.value
                if isinstance(val, ast.Constant):
                    names.append(str(val.value))
                elif isinstance(val, (ast.List, ast.Tuple)):
                    for elt in val.elts:
                        if isinstance(elt, ast.Constant):
                            names.append(str(elt.value))
    return names


def parse_odoo_xml_ids(odoo_path: Path) -> dict[str, str]:
    """Extract xml_ids from Odoo source XML data files."""
    try:
        from lxml import etree
    except ImportError:
        return {}

    xml_ids: dict[str, str] = {}
    xml_files = [
        p for p in odoo_path.rglob("*.xml")
        if not _should_skip_dir(p)
    ]

    for xml_file in xml_files:
        # Only look at data/ and security/ directories
        if not any(part in ("data", "security", "views", "report") for part in xml_file.parts):
            continue
        try:
            tree = etree.parse(str(xml_file))
        except Exception:
            continue

        module_name = _guess_module_name(xml_file, odoo_path)
        for elem in tree.iter():
            elem_id = elem.get("id")
            if not elem_id:
                continue
            full_id = f"{module_name}.{elem_id}" if "." not in elem_id else elem_id
            model = None
            if elem.tag == "record":
                model = elem.get("model")
            elif elem.tag == "menuitem":
                model = "ir.ui.menu"
            elif elem.tag == "template":
                model = "ir.ui.view"
            if model and full_id not in xml_ids:
                xml_ids[full_id] = model

    return xml_ids


def _guess_module_name(xml_file: Path, odoo_path: Path) -> str:
    """Guess the Odoo module name from the XML file's path."""
    try:
        rel = xml_file.relative_to(odoo_path)
        # rel = addons/sale/views/... → module = "sale"
        parts = rel.parts
        if len(parts) >= 2 and parts[0] in ("addons", "odoo"):
            return parts[1] if parts[0] == "addons" else parts[0]
        return parts[0]
    except ValueError:
        return "unknown"


# ─── RPC mode ──────────────────────────────────────────────────────────────

def build_stubs_from_rpc(
    url: str, db: str, username: str, password: str, version: str
) -> dict:
    """Connect to a live Odoo instance via XML-RPC and extract model metadata."""
    try:
        import xmlrpc.client as xmlrpc
    except ImportError:
        raise RuntimeError("xmlrpc.client not available (should be in stdlib)")

    print(f"Connecting to {url} (db={db}, user={username})...")

    common = xmlrpc.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise RuntimeError(f"Authentication failed for user '{username}'")

    models_proxy = xmlrpc.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model, method, *args, **kwargs):
        return models_proxy.execute_kw(db, uid, password, model, method, args, kwargs)

    print("Fetching model list from ir.model...")
    ir_models = call(
        "ir.model", "search_read",
        [[("transient", "=", False)]],
        fields=["model", "name"],
        limit=0,
    )

    result_models: dict[str, dict] = {}
    for ir_m in ir_models:
        model_name = ir_m["model"]
        result_models[model_name] = {"fields": [], "methods": []}

    print(f"Found {len(ir_models)} models. Fetching fields...")
    ir_fields = call(
        "ir.model.fields", "search_read",
        [[("store", "=", True), ("ttype", "not in", ["one2many"])]],
        fields=["model_id", "name", "ttype"],
        limit=0,
    )

    for ir_f in ir_fields:
        model_name_pair = ir_f.get("model_id")
        if not model_name_pair:
            continue
        # model_id is [id, display_name] — we need the actual model technical name
        # Fetch via a join isn't possible directly, so we stored model names above
        # Use the already-known models list
        field_name = ir_f["name"]
        # We need to find the model technical name; ir.model.fields has model field
    
    # Better approach: fetch fields per model in one batch call
    ir_fields2 = call(
        "ir.model.fields", "search_read",
        [[("store", "=", True)]],
        fields=["model", "name"],
        limit=0,
    )
    for ir_f in ir_fields2:
        m = ir_f.get("model", "")
        fname = ir_f.get("name", "")
        if m in result_models and fname and not fname.startswith("_"):
            if fname not in result_models[m]["fields"]:
                result_models[m]["fields"].append(fname)

    print("Fetching XML IDs from ir.model.data...")
    ir_data = call(
        "ir.model.data", "search_read",
        [[("model", "!=", False)]],
        fields=["module", "name", "model"],
        limit=0,
    )
    xml_ids: dict[str, str] = {}
    for rec in ir_data:
        full_id = f"{rec['module']}.{rec['name']}"
        xml_ids[full_id] = rec["model"]

    # Filter empty models
    result_models = {k: v for k, v in result_models.items() if v["fields"] or v["methods"]}

    return {"version": version, "models": result_models, "xml_ids": xml_ids}


# ─── CLI ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate odoo-doctor stub JSON from Odoo source or live instance."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Source mode
    src = subparsers.add_parser("source", help="Parse Odoo source directory (offline)")
    src.add_argument("--odoo-path", required=True, help="Path to Odoo source root")
    src.add_argument("--version", required=True, help="Odoo version string (e.g. 17.0)")
    src.add_argument("--output", default=None, help="Output JSON path (default: auto)")

    # RPC mode
    rpc = subparsers.add_parser("rpc", help="Connect to live Odoo via XML-RPC")
    rpc.add_argument("--rpc-url", required=True, help="Odoo base URL (e.g. http://localhost:8069)")
    rpc.add_argument("--rpc-db", required=True, help="Database name")
    rpc.add_argument("--rpc-user", default="admin", help="Username")
    rpc.add_argument("--rpc-password", required=True, help="Password")
    rpc.add_argument("--version", required=True, help="Odoo version string (e.g. 17.0)")
    rpc.add_argument("--output", default=None, help="Output JSON path (default: auto)")

    args = parser.parse_args(argv)

    if args.mode == "source":
        odoo_path = Path(args.odoo_path)
        if not odoo_path.exists():
            print(f"ERROR: {odoo_path} does not exist", file=sys.stderr)
            sys.exit(1)

        print(f"Parsing Odoo source at {odoo_path} for version {args.version}...")
        models = parse_odoo_source(odoo_path)
        xml_ids = parse_odoo_xml_ids(odoo_path)
        data = {"version": args.version, "models": models, "xml_ids": xml_ids}

    elif args.mode == "rpc":
        data = build_stubs_from_rpc(
            url=args.rpc_url,
            db=args.rpc_db,
            username=args.rpc_user,
            password=args.rpc_password,
            version=args.version,
        )

    out_path = args.output
    if out_path is None:
        out_path = str(Path(__file__).parent / "data" / f"{args.version}.json")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    model_count = len(data["models"])
    xml_count = len(data.get("xml_ids", {}))
    print(f"✓ Wrote {model_count} models, {xml_count} XML IDs → {out}")


if __name__ == "__main__":
    main()
