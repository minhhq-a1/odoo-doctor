# src/odoo_doctor/graph/resolver.py
"""Confidence-aware symbol resolver: repo -> stubs -> source_path -> UNKNOWN."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from odoo_doctor.graph.source_index import build_source_index
from odoo_doctor.graph.stubs.loader import load_stubs

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
ORM_MAGIC_FIELDS = frozenset(
    {
        "id",
        "display_name",
        "create_uid",
        "create_date",
        "write_uid",
        "write_date",
        "__last_update",
    }
)


# Public methods of ``BaseModel`` (Odoo 19), present on every model, so no model has to
# define them: a button may call ``unlink`` or ``action_archive`` on any model.
ORM_BASE_METHODS = frozenset(
    {
        "action_archive",
        "action_unarchive",
        "browse",
        "check_access",
        "check_access_rights",
        "check_access_rule",
        "check_field_access_rights",
        "concat",
        "copy",
        "copy_data",
        "copy_translations",
        "create",
        "default_get",
        "ensure_one",
        "exists",
        "export_data",
        "fetch",
        "fields_get",
        "filtered",
        "filtered_domain",
        "flush_model",
        "flush_recordset",
        "get_base_url",
        "get_external_id",
        "get_field_translations",
        "get_metadata",
        "get_property_definition",
        "grouped",
        "has_access",
        "invalidate_model",
        "invalidate_recordset",
        "load",
        "lock_for_update",
        "mapped",
        "modified",
        "name_create",
        "name_search",
        "new",
        "onchange",
        "read",
        "read_group",
        "search",
        "search_count",
        "search_fetch",
        "search_read",
        "sorted",
        "sudo",
        "toggle_active",
        "try_lock_for_update",
        "union",
        "unlink",
        "update",
        "update_field_translations",
        "with_company",
        "with_context",
        "with_env",
        "with_prefetch",
        "with_user",
        "write",
    }
)


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

_ALWAYS_AVAILABLE = {"base", "ir", "res"}


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
        module_dependencies: dict[str, list[str]] | None = None,
        module_licenses: dict[str, str] | None = None,
        module_external_python: dict[str, set[str]] | None = None,
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
        self._rule_models: set[str] | None = None
        self._by_underscore: dict[str, list[str]] | None = None
        # module -> declared depends, for modules whose manifest we have seen
        # (scanned addons, plus the Odoo source checkout when configured).
        self._module_dependencies: dict[str, list[str]] = dict(
            self._source_index.module_depends
        )
        self._module_dependencies.update(module_dependencies or {})
        # Manifest facts of the scanned addons (supply-chain rules).
        self._module_licenses: dict[str, str] = dict(module_licenses or {})
        self._module_external_python: dict[str, set[str]] = dict(
            module_external_python or {}
        )

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

    def _ancestor_has(
        self, model_name: str, member: str, kind: str, _seen: set[str]
    ) -> bool:
        """True if a repo model's _inherit/_inherits ancestor provides the member.

        Covers prototype inheritance (`_inherit = "a"` + a new `_name`), where the new
        model copies every field and method of its parents.
        """
        repo_model = self._repo_models.get(model_name)
        if repo_model is None:
            return False
        for anc in list(repo_model.inherit) + list(repo_model.inherits.keys()):
            if anc == model_name or anc in _seen:
                continue
            _seen.add(anc)
            resolve = self.resolve_field if kind == "field" else self.resolve_method
            if resolve(anc, member, _seen).status == ResolveResult.FOUND:
                return True
        return False

    def resolve_field(
        self, model_name: str, field_name: str, _seen: set[str] | None = None
    ) -> SymbolLookup:
        _seen = {model_name} if _seen is None else _seen | {model_name}
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

        # 3b. Fields inherited from ancestors (prototype inheritance / _inherits)
        if self._ancestor_has(model_name, field_name, "field", _seen):
            return SymbolLookup(ResolveResult.FOUND, "repo")

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

    def resolve_method(
        self, model_name: str, method_name: str, _seen: set[str] | None = None
    ) -> SymbolLookup:
        _seen = {model_name} if _seen is None else _seen | {model_name}
        # 1. Repo model's own methods
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None and method_name in repo_model.methods:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Methods added to the model via _inherit elsewhere in the repo
        ext = self._extended_methods.get(model_name)
        if ext and method_name in ext:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2b. Methods inherited from ancestors (prototype inheritance / _inherits)
        if self._ancestor_has(model_name, method_name, "method", _seen):
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2c. Methods every model gets from BaseModel (unlink, action_archive, ...)
        if method_name in ORM_BASE_METHODS:
            return SymbolLookup(ResolveResult.FOUND, "builtin")

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

    def _model_is_complete(
        self, model_name: str, _seen: set[str] | None = None
    ) -> bool:
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

        # 3. Implicit ir.model xml ids: Odoo registers `<module>.model_<model_name
        #    with dots as underscores>` for every model, with no XML declaration.
        if self._is_implicit_model_xml_id(xml_id):
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 4. Implicit ir.model.fields xml ids: `<module>.field_<model with dots as
        #    underscores>__<field>` exists for every field of every model.
        if self._is_implicit_field_xml_id(xml_id):
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # XML IDs are module-scoped; we can't prove absence without full knowledge
        return SymbolLookup(ResolveResult.UNKNOWN)

    def model_has_record_rule(self, model_name: str) -> bool:
        """True if any scanned module declares an `ir.rule` for the model."""
        if self._rule_models is None:
            by_suffix = {m.replace(".", "_"): m for m in self._repo_models}
            self._rule_models = set()
            for info in self._repo_xml_ids.values():
                if getattr(info, "model", None) != "ir.rule":
                    continue
                for ref in getattr(info, "refs", []):
                    name = ref.rpartition(".")[2]
                    if name.startswith("model_") and name[6:] in by_suffix:
                        self._rule_models.add(by_suffix[name[6:]])
        return model_name in self._rule_models

    def _is_implicit_model_xml_id(self, xml_id: str) -> bool:
        _module, _, name = xml_id.rpartition(".")
        if not name.startswith("model_"):
            return False
        suffix = name[len("model_") :]
        return any(m.replace(".", "_") == suffix for m in self._repo_models)

    def _models_by_underscore_name(self) -> dict[str, list[str]]:
        """Model names indexed by their ``field_``/``model_`` xml id form (dots -> ``_``)."""
        if self._by_underscore is None:
            names = set(self._repo_models)
            if self._stubs:
                names.update(self._stubs.models)
            index: dict[str, list[str]] = {}
            for name in names:
                index.setdefault(name.replace(".", "_"), []).append(name)
            self._by_underscore = index
        return self._by_underscore

    def _is_implicit_field_xml_id(self, xml_id: str) -> bool:
        _module, _, name = xml_id.rpartition(".")
        if not name.startswith("field_") or "__" not in name:
            return False
        model_part, _, field_name = name[len("field_") :].partition("__")
        return any(
            self.resolve_field(model_name, field_name).status == ResolveResult.FOUND
            for model_name in self._models_by_underscore_name().get(model_part, [])
        )

    def resolve_xml_id_for_module(
        self, xml_id: str, current_module: str
    ) -> SymbolLookup:
        lookup = self.resolve_xml_id(xml_id)
        if lookup.status != ResolveResult.UNKNOWN:
            return lookup
        if "." not in xml_id or xml_id.split(".", 1)[0] == current_module:
            return SymbolLookup(ResolveResult.LOCAL_NOT_FOUND)
        return lookup

    def module_is_known(self, module: str) -> bool:
        """Check if a module is known to the system via repo models, xml_ids, overrides, or builtin."""
        if module in _ALWAYS_AVAILABLE:
            return True
        if module in _MODEL_OWNER_OVERRIDES.values():
            return True
        # any repo model whose module == module
        if any(model.module == module for model in self._repo_models.values()):
            return True
        # any repo xml_id with prefix f"{module}."
        if any(xml_id.startswith(f"{module}.") for xml_id in self._repo_xml_ids):
            return True
        # any stub xml_id with prefix f"{module}."
        if self._stubs and any(
            xml_id.startswith(f"{module}.") for xml_id in self._stubs.xml_ids
        ):
            return True
        return False

    def dependency_closure(self, depends: list[str]) -> tuple[set[str], bool]:
        """Transitive closure of `depends` over every manifest we know about.

        Returns (modules, complete). `complete` is False when some module in the
        closure has no manifest we have seen (e.g. a core module without a
        configured odoo_source_path), so its own dependencies are unknown and the
        closure may be missing modules.
        """
        closure: set[str] = set()
        complete = True
        todo = list(depends)
        while todo:
            mod = todo.pop()
            if mod in closure:
                continue
            closure.add(mod)
            if mod in _ALWAYS_AVAILABLE:
                continue
            deps = self._module_dependencies.get(mod)
            if deps is None:
                complete = False
            else:
                todo.extend(deps)
        return closure, complete

    def module_license(self, module: str) -> str | None:
        """Declared manifest license of a scanned addon, if any."""
        return self._module_licenses.get(module)

    def module_external_python(self, module: str) -> set[str] | None:
        """Lower-cased top-level names a scanned addon declares as python
        external_dependencies, or None when its manifest was not scanned."""
        return self._module_external_python.get(module)

    def is_known_module(self, module: str) -> bool:
        """True if the module's manifest was scanned (repo or odoo_source_path)."""
        return module in self._module_dependencies
