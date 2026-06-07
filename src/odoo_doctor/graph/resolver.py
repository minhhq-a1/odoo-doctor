# src/odoo_doctor/graph/resolver.py
"""Confidence-aware symbol resolver: repo -> stubs -> source_path -> UNKNOWN."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from odoo_doctor.graph.stubs.loader import load_stubs
from odoo_doctor.graph.source_index import build_source_index

if TYPE_CHECKING:
    from odoo_doctor.parsers.python_models import ModelInfo


class ResolveResult(Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    LOCAL_NOT_FOUND = "local_not_found"
    UNKNOWN = "unknown"


@dataclass
class SymbolLookup:
    status: ResolveResult
    source: str | None = None  # "repo" | "stub" | "source_path"


_MODEL_OWNER_OVERRIDES = {
    "sale.order": "sale",
    "sale.order.line": "sale",
    "purchase.order": "purchase",
    "stock.picking": "stock",
    "account.move": "account",
    "product.template": "product",
    "product.product": "product",
    "mail.thread": "mail",
}


class SymbolResolver:
    """Resolve models, fields, methods, and XML IDs across the project.

    Resolution order: repo symbols -> packaged stubs -> optional source path -> UNKNOWN.
    """

    def __init__(
        self,
        repo_models: dict[str, ModelInfo],
        repo_xml_ids: dict[str, object],
        stub_version: str,
        source_path: str | None = None,
        extended_fields: dict[str, dict] | None = None,
    ):
        self._repo_models = repo_models
        self._repo_xml_ids = repo_xml_ids
        self._stubs = load_stubs(stub_version)
        self._source_path = source_path
        # extended_fields: {model_name: {field_name: FieldInfo}} from _inherit-only extensions
        # These are fields added to stub-known models (e.g. custom_note on sale.order)
        self._extended_fields: dict[str, dict] = extended_fields or {}
        self._source_index = build_source_index(source_path)

    def resolve_model(self, model_name: str) -> SymbolLookup:
        # 1. Repo
        if model_name in self._repo_models:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs and model_name in self._stubs.models:
            return SymbolLookup(ResolveResult.FOUND, "stub")

        # 3. Source path
        if self._source_index and model_name in self._source_index.model_owners:
            return SymbolLookup(ResolveResult.FOUND, "source_path")

        # 4. Unknown — we can't say it doesn't exist
        return SymbolLookup(ResolveResult.UNKNOWN)

    def owner_module_for_model(self, model_name: str) -> SymbolLookup:
        # 1. Repo
        if model_name in self._repo_models:
            model_info = self._repo_models[model_name]
            if model_info.module:
                return SymbolLookup(ResolveResult.FOUND, model_info.module)

        # 2. Source index
        if hasattr(self, "_source_index") and self._source_index:
            owner = self._source_index.model_owners.get(model_name)
            if owner:
                return SymbolLookup(ResolveResult.FOUND, owner)

        # 3. Fallback overrides
        if model_name in _MODEL_OWNER_OVERRIDES:
            return SymbolLookup(ResolveResult.FOUND, _MODEL_OWNER_OVERRIDES[model_name])

        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_field(self, model_name: str, field_name: str) -> SymbolLookup:
        # 1. Repo (native model with _name)
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None:
            if field_name in repo_model.fields:
                return SymbolLookup(ResolveResult.FOUND, "repo")
            # Model known in repo but field not there — check stubs too
            # (model may inherit fields from core that aren't in the repo code)

        # 1b. Extended fields from _inherit-only extensions in the repo
        ext = self._extended_fields.get(model_name)
        if ext and field_name in ext:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None:
                if field_name in stub_model.get("fields", []):
                    return SymbolLookup(ResolveResult.FOUND, "stub")
                # Model is known (repo or stub) and field not found anywhere
                if repo_model is not None or stub_model is not None:
                    return SymbolLookup(ResolveResult.NOT_FOUND)

        # If model found in repo only (no stub for it), field not in repo
        if repo_model is not None:
            # We know the model but stubs don't cover it — could have
            # inherited fields we don't see. Be conservative.
            return SymbolLookup(ResolveResult.UNKNOWN)

        # Model not known at all
        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_method(self, model_name: str, method_name: str) -> SymbolLookup:
        # 1. Repo
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None and method_name in repo_model.methods:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None:
                if method_name in stub_model.get("methods", []):
                    return SymbolLookup(ResolveResult.FOUND, "stub")
                # Model known, method not found
                if repo_model is not None or stub_model is not None:
                    return SymbolLookup(ResolveResult.NOT_FOUND)

        if repo_model is not None:
            return SymbolLookup(ResolveResult.UNKNOWN)

        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_xml_id(self, xml_id: str) -> SymbolLookup:
        # 1. Repo
        if xml_id in self._repo_xml_ids:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs and xml_id in self._stubs.xml_ids:
            return SymbolLookup(ResolveResult.FOUND, "stub")

        # XML IDs are module-scoped; we can't prove absence without full knowledge
        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_xml_id_for_module(self, xml_id: str, current_module: str) -> SymbolLookup:
        lookup = self.resolve_xml_id(xml_id)
        if lookup.status != ResolveResult.UNKNOWN:
            return lookup
        if "." not in xml_id or xml_id.split(".", 1)[0] == current_module:
            return SymbolLookup(ResolveResult.LOCAL_NOT_FOUND)
        return lookup
