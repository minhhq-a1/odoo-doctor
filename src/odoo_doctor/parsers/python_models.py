# src/odoo_doctor/parsers/python_models.py
"""Parse Odoo Python models and controllers using stdlib ast."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from odoo_doctor.core.source import parse_python, read_source


@dataclass
class FieldInfo:
    name: str
    field_type: str  # "Char", "Many2one", "Float", etc.
    comodel: str | None = None
    compute: str | None = None
    depends: list[str] = field(default_factory=list)
    store: bool = True
    required: bool = False
    string: str | None = None
    ondelete: str | None = None
    currency_field: str | None = None  # Monetary only
    related: str | None = None
    line: int = 0


@dataclass
class MethodInfo:
    name: str
    decorators: list[str] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
    is_override: bool = False
    calls_super: bool = False
    # The body raises on every path that returns nothing: the operation is blocked.
    always_raises: bool = False
    # Calls the method of the same name on another receiver (`tmpl.copy(...)`, not `self`).
    delegates: bool = False
    line: int = 0


@dataclass
class ModelInfo:
    name: str | None  # _name value, None if only _inherit
    inherit: list[str] = field(default_factory=list)
    inherits: dict[str, str] = field(default_factory=dict)
    fields: dict[str, FieldInfo] = field(default_factory=dict)
    methods: dict[str, MethodInfo] = field(default_factory=dict)
    is_transient: bool = False
    is_abstract: bool = False
    file_path: str = ""
    line: int = 0
    module: str = ""
    # True when a class defines the model: it has a `_name` that its own `_inherit` does not
    # list. `_name = 'x'` with `_inherit = ['x', mixin]` (and `_inherit = 'x'` alone) extends.
    defines: bool = False
    # False when the class sets `_auto = False`: no table is created by the ORM, so the
    # default `create`/`write` behind `super()` has nothing to store into.
    auto_table: bool = True
    # `_inherit` / `_inherits` is not a literal (a name, a computed list, `*args`): the parents
    # are not all known, so the model's symbols cannot be proven complete.
    inherit_unresolved: bool = False


@dataclass
class ControllerInfo:
    method_name: str
    route: str
    # The auth the route runs with: the decorator's literal, else the parent route's (see
    # ``resolve_route_auth``), else "user" (the default of a route with no parent). "unknown"
    # when the decorator computes it or the parent route lies outside the scanned code.
    auth: str = "user"
    # What the decorator says: the literal, "unknown" for a computed value, None when absent.
    declared_auth: str | None = None
    uses_sudo: bool = False
    # A call that checks access (token comparison, signature, record access check).
    guarded: bool = False
    file_path: str = ""
    line: int = 0


@dataclass
class ControllerClass:
    """A class that may carry routes, with the bases that route inheritance walks."""

    name: str
    bases: list[str] = field(default_factory=list)  # last component of each base
    routes: dict[str, ControllerInfo] = field(default_factory=dict)  # by method name


# --- Odoo base class names ---
# `models.BaseModel` is the base of SQL-view / report models (`_auto = False`).
_MODEL_BASES = {"models.Model", "Model", "models.BaseModel", "BaseModel"}
_TRANSIENT_BASES = {"models.TransientModel", "TransientModel"}
_ABSTRACT_BASES = {"models.AbstractModel", "AbstractModel"}
_ALL_BASES = _MODEL_BASES | _TRANSIENT_BASES | _ABSTRACT_BASES

_ODOO_FIELD_TYPES = {
    "Char",
    "Text",
    "Html",
    "Integer",
    "Float",
    "Boolean",
    "Date",
    "Datetime",
    "Binary",
    "Selection",
    "Many2one",
    "One2many",
    "Many2many",
    "Monetary",
    "Reference",
    "Image",
    "Json",
    "Many2oneReference",
    "Properties",
    "PropertiesDefinition",
}


def _is_field_class(func_name: str, short: str) -> bool:
    """A call that declares a field: a known Odoo field class, or any ``fields.<Class>``.

    The second form covers field classes other modules add to ``odoo.fields`` (for example
    ``fields.Serialized`` from ``base_sparse_field``). ``fields.Date.today()`` is a call on a
    field class and ``fields.helper()`` is lower-case, so neither matches.
    """
    if short in _ODOO_FIELD_TYPES:
        return True
    return (
        func_name.count(".") == 1
        and func_name.startswith("fields.")
        and short[:1].isupper()
    )


_LIFECYCLE_METHODS = {"create", "write", "unlink", "default_get", "read", "copy"}


def parse_models(file_path: Path) -> list[ModelInfo]:
    """Parse all Odoo model classes from a Python file."""
    tree = parse_python(file_path)
    if tree is None:
        return []

    models: list[ModelInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_odoo_model(node):
            continue
        models.append(_extract_model(node, str(file_path)))
    return models


def parse_controller_classes(file_path: Path) -> list[ControllerClass]:
    """Every class of a file that has a base (and so may inherit routes), with its routes."""
    tree = parse_python(file_path)
    if tree is None:
        return []
    source = read_source(file_path) or ""

    classes: list[ControllerClass] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or _is_odoo_model(node):
            continue
        cls = ControllerClass(
            name=node.name,
            bases=[(_dotted_name(b) or "").rsplit(".", 1)[-1] for b in node.bases],
        )
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_info = _extract_route(item)
            if route_info is None:
                continue
            route, declared = route_info
            cls.routes[item.name] = ControllerInfo(
                method_name=item.name,
                route=route,
                auth=declared or "user",
                declared_auth=declared,
                uses_sudo=_body_uses_sudo(item, source),
                guarded=_body_checks_access(item),
                file_path=str(file_path),
                line=item.lineno,
            )
        if cls.routes or cls.bases:
            classes.append(cls)
    return classes


def parse_controllers(file_path: Path) -> list[ControllerInfo]:
    """Parse all http.route controllers from a Python file.

    A route that declares no ``auth`` is resolved against the parents found in this file only;
    the project graph resolves it across files and modules.
    """
    classes = parse_controller_classes(file_path)
    resolve_route_auth(classes)
    return [route for cls in classes for route in cls.routes.values()]


_END_OF_CHAIN = {"Controller", "object"}


def resolve_route_auth(classes: list[ControllerClass]) -> None:
    """Give every route without ``auth`` the auth of the route it overrides.

    Odoo merges the routing of an overridden handler into the override, so ``@route()`` or
    ``@route('/x', website=True)`` keeps the parent's ``auth='public'``. Parents are found
    by class name among ``classes``, in base order. A base that is not among them (a class
    of an addon that is not scanned) may define the route, so the auth is "unknown"; a chain
    that ends at ``http.Controller`` without a parent route runs with the default, "user".
    """
    by_name: dict[str, list[ControllerClass]] = {}
    for cls in classes:
        by_name.setdefault(cls.name, []).append(cls)
    memo: dict[tuple[int, str], str | None] = {}

    def effective(cls: ControllerClass, method: str) -> str:
        info = cls.routes[method]
        if info.declared_auth is not None:
            return info.declared_auth
        return inherited(cls, method) or "user"

    def inherited(cls: ControllerClass, method: str) -> str | None:
        """Auth of the route ``method`` that ``cls`` overrides; None if it has no parent."""
        key = (id(cls), method)
        if key in memo:
            return memo[key]
        memo[key] = None  # a cycle of same-named classes ends here
        found: str | None = None
        for base in cls.bases:
            parents = [c for c in by_name.get(base, []) if c is not cls]
            if not parents and base in _END_OF_CHAIN:
                continue
            if not parents:
                found = "unknown"
                break
            autos = {
                effective(p, method) if method in p.routes else inherited(p, method)
                for p in parents
            } - {None}
            if autos:
                found = autos.pop() if len(autos) == 1 else "unknown"
                break
        memo[key] = found
        return found

    for cls in classes:
        for method, info in cls.routes.items():
            info.auth = effective(cls, method)


# --- Helpers ---


def _is_odoo_model(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        name = _dotted_name(base)
        if name and name in _ALL_BASES:
            return True
    return False


def _extract_model(cls: ast.ClassDef, file_path: str) -> ModelInfo:
    model = ModelInfo(name=None, file_path=file_path, line=cls.lineno)

    # Detect transient/abstract
    for base in cls.bases:
        name = _dotted_name(base)
        if name in _TRANSIENT_BASES:
            model.is_transient = True
        elif name in _ABSTRACT_BASES:
            model.is_abstract = True

    for item in cls.body:
        # _name, _inherit, _inherits assignments
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    if target.id == "_name" and isinstance(item.value, ast.Constant):
                        model.name = item.value.value
                    elif target.id == "_auto" and isinstance(item.value, ast.Constant):
                        model.auto_table = bool(item.value.value)
                    elif target.id == "_inherit":
                        model.inherit, literal = _extract_inherit(item.value)
                        model.inherit_unresolved |= not literal
                    elif target.id == "_inherits":
                        model.inherit_unresolved |= not _extract_inherits(
                            item.value, model.inherits
                        )

        # Field definitions
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                field_info = _extract_field(target.id, item.value, item.lineno)
                if field_info:
                    model.fields[field_info.name] = field_info

        # Annotated field definitions: `parent_id: Cat = fields.Many2one(...)` (Odoo 19 core)
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and isinstance(item.value, ast.Call)
        ):
            field_info = _extract_field(item.target.id, item.value, item.lineno)
            if field_info:
                model.fields[field_info.name] = field_info

        # Method definitions
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method = _extract_method(item)
            model.methods[method.name] = method

    model.defines = model.name is not None and model.name not in model.inherit
    return model


def _extract_inherit(node: ast.expr) -> tuple[list[str], bool]:
    """The parents named by ``_inherit`` (string, list or tuple), and whether all are literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value], True
    if isinstance(node, (ast.List, ast.Tuple)):
        names = [
            e.value
            for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        return names, len(names) == len(node.elts)
    return [], isinstance(node, ast.Constant) and node.value is None


def _extract_inherits(node: ast.expr, into: dict[str, str]) -> bool:
    """Fill ``into`` from a literal ``_inherits`` dict; False when some entry is not literal."""
    if not isinstance(node, ast.Dict):
        return False
    literal = True
    for k, v in zip(node.keys, node.values):
        if (
            isinstance(k, ast.Constant)
            and isinstance(k.value, str)
            and isinstance(v, ast.Constant)
        ):
            into[k.value] = v.value
        else:
            literal = False
    return literal


def _extract_field(name: str, call: ast.Call, line: int = 0) -> FieldInfo | None:
    func_name = _dotted_name(call.func)
    if func_name is None:
        return None

    # Strip "fields." prefix
    short = func_name.split(".")[-1] if "." in func_name else func_name
    if not _is_field_class(func_name, short):
        return None

    comodel = None
    compute = None
    depends: list[str] = []
    explicit_store: bool | None = None
    related = None
    computed_or_related = False
    required = False
    string = None
    ondelete = None
    currency_field = None

    # First positional arg for relational fields is comodel
    # For Char/etc, the first positional arg is actually the string, but Odoo 14+
    # conventions encourage kwargs. To be safe, if we see a string as arg[0] on non-relational:
    if call.args and isinstance(call.args[0], ast.Constant):
        if short in ("Many2one", "One2many", "Many2many"):
            comodel = call.args[0].value
        elif isinstance(call.args[0].value, str):
            string = call.args[0].value

    for kw in call.keywords:
        if kw.arg == "comodel_name" and isinstance(kw.value, ast.Constant):
            comodel = kw.value.value
        elif kw.arg == "compute" and isinstance(kw.value, ast.Constant):
            compute = kw.value.value
        elif kw.arg == "related" and isinstance(kw.value, ast.Constant):
            related = kw.value.value
        elif kw.arg == "store" and isinstance(kw.value, ast.Constant):
            explicit_store = bool(kw.value.value)
        elif kw.arg == "required" and isinstance(kw.value, ast.Constant):
            required = bool(kw.value.value)
        elif kw.arg == "string" and isinstance(kw.value, ast.Constant):
            string = str(kw.value.value)
        elif kw.arg == "ondelete" and isinstance(kw.value, ast.Constant):
            ondelete = kw.value.value
        elif kw.arg == "currency_field" and isinstance(kw.value, ast.Constant):
            currency_field = kw.value.value

    for kw in call.keywords:
        if kw.arg in ("compute", "related"):  # whatever the value is (a name, a lambda)
            computed_or_related = True
    # Odoo stores a field unless it is computed or related; `store=` overrides either way.
    store = explicit_store if explicit_store is not None else not computed_or_related

    return FieldInfo(
        name=name,
        field_type=short,
        comodel=comodel,
        compute=compute,
        related=related,
        depends=depends,
        store=store,
        required=required,
        string=string,
        ondelete=ondelete,
        currency_field=currency_field,
        line=line,
    )


def _extract_method(func: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
    decorators: list[str] = []
    depends: list[str] = []

    for dec in func.decorator_list:
        dec_name = (
            _dotted_name(dec)
            if not isinstance(dec, ast.Call)
            else _dotted_name(dec.func)
        )
        if dec_name:
            decorators.append(dec_name)
        # Extract @api.depends("field1", "field2")
        if isinstance(dec, ast.Call) and _dotted_name(dec.func) == "api.depends":
            for arg in dec.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    depends.append(arg.value)

    is_override = func.name in _LIFECYCLE_METHODS
    calls_super = _body_calls_super(func)

    return MethodInfo(
        name=func.name,
        decorators=decorators,
        depends=depends,
        is_override=is_override,
        calls_super=calls_super,
        always_raises=_body_always_raises(func),
        delegates=_body_delegates(func),
        line=func.lineno,
    )


def _is_super_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "super"
    )


def _body_calls_super(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """``super().<func.name>`` is reached; ``super().write()`` inside ``create`` is not.

    shortcut: a ``super()`` that is stored or passed on (``parent = super()``) is trusted
    to be used for this method, when it could be followed through the local.
    """
    accessed: set[int] = set()  # super() calls used as `super().<attr>`
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and _is_super_call(node.value):
            if node.attr == func.name:
                return True
            accessed.add(id(node.value))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "super"
        ):
            return True
    return any(_is_super_call(n) and id(n) not in accessed for n in ast.walk(func))


def _body_always_raises(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A top-level ``raise`` and no ``return`` anywhere: the method never completes."""
    return any(isinstance(n, ast.Raise) for n in func.body) and not any(
        isinstance(n, ast.Return) for n in ast.walk(func)
    )


# Methods that return records of the same model: a call on them is still a call on self.
_SAME_MODEL_ADAPTERS = {
    "sudo",
    "with_context",
    "with_user",
    "with_company",
    "with_env",
    "browse",
    "exists",
    "filtered",
    "filtered_domain",
    "sorted",
}


def _strip_adapters(node: ast.expr) -> ast.expr:
    while (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _SAME_MODEL_ADAPTERS
    ):
        node = node.func.value
    return node


def _body_delegates(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Calls its own name on records of another model that it maps out of ``self``.

    That is a receiver chain such as ``self.mapped('tmpl_id')`` / ``self.line_ids``, or a
    local built from ``self`` (``tmpls = self.env['t'].concat(*[r.t for r in self])``).
    ``self`` itself, its same-model adapters (``self.sudo()``), and anything that only
    looks a model up in ``env`` (``self.env['m'].browse(1)``) are not delegation.

    shortcut: a local reassigned in a loop is judged by every assignment alike, when a
    flow analysis could follow one value at a time.
    """
    assigns = [
        (t.id, n.value)
        for n in ast.walk(func)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    ]
    derived: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, value in assigns:
            if name in derived:
                continue
            value = _strip_adapters(value)
            if isinstance(value, ast.Name) and value.id == "self":
                continue
            env_roots = {
                id(n.value)
                for n in ast.walk(value)
                if isinstance(n, ast.Attribute)
                and n.attr == "env"
                and isinstance(n.value, ast.Name)
            }
            if any(
                isinstance(n, ast.Name)
                and ((n.id == "self" and id(n) not in env_roots) or n.id in derived)
                for n in ast.walk(value)
            ):
                derived.add(name)
                changed = True
    for node in ast.walk(func):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == func.name
        ):
            continue
        recv = node.func.value
        if isinstance(recv, ast.Name) and recv.id in derived:
            return True
        attrs, base = [], recv
        while isinstance(base, (ast.Attribute, ast.Call, ast.Subscript)):
            if isinstance(base, ast.Attribute):
                attrs.append(base.attr)
            base = base.func if isinstance(base, ast.Call) else base.value
        if (
            attrs  # not bare `self`
            and isinstance(base, ast.Name)
            and base.id == "self"
            and "env" not in attrs
            and not set(attrs) <= _SAME_MODEL_ADAPTERS
        ):
            return True
    return False


def _body_uses_sudo(func: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> bool:
    """Does the route elevate privileges?

    ``.sudo(False)`` drops them, and ``env['ir.config_parameter'].sudo().get_param('k')``
    with a constant key only reads a setting a public user cannot otherwise reach: neither
    is an elevation worth reporting.
    """
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(func):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "sudo":
            continue
        values = [*node.args[:1], *(k.value for k in node.keywords)]
        if any(isinstance(v, ast.Constant) and v.value is False for v in values):
            continue
        if _is_constant_config_read(node, parents):
            continue
        return True
    return False


def _is_constant_config_read(sudo: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    receiver = sudo.func.value  # type: ignore[attr-defined]
    on_config = (
        isinstance(receiver, ast.Subscript)
        and isinstance(receiver.slice, ast.Constant)
        and receiver.slice.value == "ir.config_parameter"
    )
    attr = parents.get(sudo)
    call = parents.get(attr) if attr is not None else None
    return bool(
        on_config
        and isinstance(attr, ast.Attribute)
        and attr.attr == "get_param"
        and isinstance(call, ast.Call)
        and call.args
        and isinstance(call.args[0], ast.Constant)
    )


# Fragments of the names of functions that enforce an access check; minting a token
# (`generate_access_token`) or computing a flag is not one.
_ACCESS_CHECK_FRAGMENTS = (
    "consteq",
    "hmac",
    "verify",
    "check_access",
    "check_token",
    "from_token",
    "validate_token",
)
_NOT_A_CHECK_PREFIXES = ("generate", "_generate", "_compute", "compute")


def _body_checks_access(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        if name.lstrip("_").startswith(_NOT_A_CHECK_PREFIXES) or not name:
            continue
        if any(fragment in name for fragment in _ACCESS_CHECK_FRAGMENTS):
            return True
    return False


def _extract_route(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, str | None] | None:
    """Route and declared auth of an @http.route decorator (auth None when not written)."""
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        dec_name = _dotted_name(dec.func)
        if dec_name not in ("http.route", "route"):
            continue
        route = ""
        auth: str | None = None
        if dec.args and isinstance(dec.args[0], ast.Constant):
            route = dec.args[0].value
        for kw in dec.keywords:
            if kw.arg == "auth":
                is_literal = isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                )
                auth = kw.value.value if is_literal else "unknown"  # type: ignore[attr-defined]
            elif kw.arg == "route" and isinstance(kw.value, ast.Constant):
                route = kw.value.value
        return route, auth
    return None


def _dotted_name(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None
