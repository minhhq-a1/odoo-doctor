# src/odoo_doctor/graph/module_context.py
"""ModuleContext and ProjectGraph — wires parsers and resolver together."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from odoo_doctor.discovery.addons import discover_addons
from odoo_doctor.discovery.odoo_version import detect_odoo_version
from odoo_doctor.graph.resolver import SymbolResolver
from odoo_doctor.parsers.manifest import ManifestData, parse_manifest
from odoo_doctor.parsers.python_models import (
    ControllerInfo,
    ModelInfo,
    parse_controllers,
    parse_models,
)
from odoo_doctor.parsers.security_csv import AccessRule, parse_access_csv
from odoo_doctor.parsers.xml_records import (
    ViewInfo,
    XmlIdInfo,
    parse_views,
    parse_xml_records,
)


@dataclass
class ModuleContext:
    name: str
    path: Path
    odoo_version: str
    manifest: ManifestData
    depends: list[str]
    models: dict[str, ModelInfo]
    xml_ids: dict[str, XmlIdInfo]  # first definition per XML ID, for resolver lookup
    xml_records: list[XmlIdInfo]  # all definitions, including duplicates
    views: list[ViewInfo]
    controllers: list[ControllerInfo]
    access_rules: list[AccessRule]
    resolver: SymbolResolver = field(repr=False)


@dataclass
class ProjectGraph:
    modules: dict[str, ModuleContext]
    resolver: SymbolResolver


def build_project_graph(
    addon_paths: list[Path],
    odoo_version: str = "unknown",
    target_modules: list[str] | None = None,
    odoo_source_path: str | None = None,
) -> ProjectGraph:
    """Discover addons, parse all inputs, build shared resolver and per-module contexts."""
    addons = discover_addons(addon_paths, target_modules=target_modules)

    # First pass: collect all models and XML IDs across all modules (for resolver)
    all_models: dict[str, ModelInfo] = {}
    all_xml_ids: dict[str, XmlIdInfo] = {}
    module_data: dict[str, dict] = {}
    # Fields extended via _inherit on stub-known models (e.g. custom_note on sale.order)
    _inherit_extensions: dict[str, dict] = {}
    # Methods extended via _inherit on stub-known models (e.g. action_foo on sale.order)
    _inherit_method_extensions: dict[str, dict] = {}

    for addon in addons:
        manifest = parse_manifest(addon.path)
        if manifest is None:
            continue

        # Detect version per module
        mod_version = detect_odoo_version(
            manifest_version=manifest.version,
        )
        if mod_version == "unknown":
            mod_version = odoo_version

        # Parse Python files
        models: dict[str, ModelInfo] = {}
        controllers: list[ControllerInfo] = []
        for py_file in addon.path.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            for m in parse_models(py_file):
                m.module = addon.name
                key = m.name or (m.inherit[0] if m.inherit else None)
                if key:
                    if key in models:
                        # Merge fields/methods from multiple files
                        models[key].fields.update(m.fields)
                        models[key].methods.update(m.methods)
                        models[key].inherit = list(set(models[key].inherit + m.inherit))
                    else:
                        models[key] = m
            controllers.extend(parse_controllers(py_file))

        # Parse XML files
        xml_ids: dict[str, XmlIdInfo] = {}
        xml_records: list[XmlIdInfo] = []
        views: list[ViewInfo] = []
        for data_file in manifest.data:
            xml_path = addon.path / data_file
            if xml_path.suffix == ".xml" and xml_path.exists():
                for rec in parse_xml_records(xml_path, module_name=addon.name):
                    xml_records.append(rec)
                    xml_ids.setdefault(rec.xml_id, rec)
                views.extend(parse_views(xml_path, module_name=addon.name))

        # Parse security CSV
        access_rules: list[AccessRule] = []
        csv_path = addon.path / "security" / "ir.model.access.csv"
        if csv_path.exists():
            access_rules = parse_access_csv(csv_path, module_name=addon.name)

        # Add models with _name to resolver repo
        for key, m in models.items():
            if m.name is not None:
                all_models[key] = m

        # Track inherit-only extensions — we'll merge them after all modules are processed
        for key, m in models.items():
            if m.name is None and m.fields:
                # key is the inherited model name (e.g. "sale.order")
                # We store the extended fields so we can merge them later
                if key not in _inherit_extensions:
                    _inherit_extensions[key] = {}
                _inherit_extensions[key].update(m.fields)
            if m.name is None and m.methods:
                if key not in _inherit_method_extensions:
                    _inherit_method_extensions[key] = {}
                _inherit_method_extensions[key].update(m.methods)

        all_xml_ids.update(xml_ids)

        module_data[addon.name] = {
            "addon": addon,
            "manifest": manifest,
            "version": mod_version,
            "models": models,
            "xml_ids": xml_ids,
            "xml_records": xml_records,
            "views": views,
            "controllers": controllers,
            "access_rules": access_rules,
        }

    # Post-loop: record all fields added to stub-known models via _inherit in the repo.
    # We pass these as 'extended_fields' to the resolver so it can resolve them as FOUND
    # WITHOUT treating the inherited model itself as a repo-defined model (which would
    # break the missing-dependency rule's source='stub' check).
    extended_fields: dict[str, dict] = _inherit_extensions
    extended_methods: dict[str, dict] = _inherit_method_extensions

    # Use the detected module version for stubs when CLI/config did not provide one.
    resolver_version = odoo_version
    if resolver_version == "unknown":
        detected_versions = {
            data["version"]
            for data in module_data.values()
            if data["version"] != "unknown"
        }
        if len(detected_versions) == 1:
            resolver_version = next(iter(detected_versions))

    # Build shared resolver
    resolver = SymbolResolver(
        repo_models=all_models,
        repo_xml_ids=all_xml_ids,
        stub_version=resolver_version,
        source_path=odoo_source_path,
        extended_fields=extended_fields,
        extended_methods=extended_methods,
    )

    # Build per-module contexts
    modules: dict[str, ModuleContext] = {}
    for name, data in module_data.items():
        modules[name] = ModuleContext(
            name=name,
            path=data["addon"].path,
            odoo_version=data["version"],
            manifest=data["manifest"],
            depends=data["manifest"].depends,
            models=data["models"],
            xml_ids=data["xml_ids"],
            xml_records=data["xml_records"],
            views=data["views"],
            controllers=data["controllers"],
            access_rules=data["access_rules"],
            resolver=resolver,
        )

    return ProjectGraph(modules=modules, resolver=resolver)
