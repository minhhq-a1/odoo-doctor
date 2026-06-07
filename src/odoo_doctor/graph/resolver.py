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


# Fields implicitly present on every Odoo model (ORM-injected). Always FOUND,
# regardless of stub contents — they never appear in curated stubs.
ORM_MAGIC_FIELDS = frozenset({
    "id",
    "display_name",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "__last_update",
})


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
        extended_methods: dict[str, dict] | None = None,
    ):
        self._repo_models = repo_models
        self._repo_xml_ids = repo_xml_ids
        self._stubs = load_stubs(stub_version)
        self._source_path = source_path
        # extended_fields: {model_name: {field_name: FieldInfo}} from _inherit-only extensions
        # These are fields added to stub-known models (e.g. custom_note on sale.order)
        self._extended_fields: dict[str, dict] = extended_fields or {}
        # extended_methods: {model_name: {method_name: MethodInfo}} — symmetric with fields,
        # so an action_* button added to sale.order via _inherit resolves FOUND.
        self._extended_methods: dict[str, dict] = extended_methods or {}
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
        # 1. Repo model's own fields
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None and field_name in repo_model.fields:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Fields added to the model via _inherit elsewhere in the repo
        ext = self._extended_fields.get(model_name)
        if ext and field_name in ext:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 3. ORM-injected magic fields (id, create_uid, ...)
        if field_name in ORM_MAGIC_FIELDS:
            return SymbolLookup(ResolveResult.FOUND, "builtin")

        # 4. Stub fields (presence only)
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None and field_name in stub_model.get("fields", []):
                return SymbolLookup(ResolveResult.FOUND, "stub")

        # 5. Provable absence: only when the model is genuinely complete.
        if self._model_is_complete(model_name):
            return SymbolLookup(ResolveResult.NOT_FOUND)

        # 6. Otherwise we cannot prove absence.
        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_method(self, model_name: str, method_name: str) -> SymbolLookup:
        # 1. Repo model's own methods
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None and method_name in repo_model.methods:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Methods added to the model via _inherit elsewhere in the repo
        ext = self._extended_methods.get(model_name)
        if ext and method_name in ext:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 3. Stub methods (presence only)
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None and method_name in stub_model.get("methods", []):
                return SymbolLookup(ResolveResult.FOUND, "stub")

        # 4. Provable absence: only when the model is genuinely complete.
        if self._model_is_complete(model_name):
            return SymbolLookup(ResolveResult.NOT_FOUND)

        # 5. Otherwise we cannot prove absence.
        return SymbolLookup(ResolveResult.UNKNOWN)

    def _model_is_complete(self, model_name: str, _seen: set[str] | None = None) -> bool:
        """A model's symbol set is provably complete (absence ⇒ NOT_FOUND) when it is
        repo-defined with every _inherit/_inherits ancestor itself complete, or it is
        backed by a stub file flagged `complete`. Partial stubs and unknown models are
        never complete."""
        if _seen is None:
            _seen = set()
        if model_name in _seen:
            return False  # cycle guard — be conservative
        _seen.add(model_name)

        repo_model = self._repo_models.get(model_name)
        if repo_model is not None:
            ancestors = list(repo_model.inherit) + list(repo_model.inherits.keys())
            for anc in ancestors:
                if anc == model_name:
                    continue
                if not self._model_is_complete(anc, _seen):
                    return False
            return True

        if self._stubs and model_name in self._stubs.models:
            return self._stubs.complete

        return False

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
