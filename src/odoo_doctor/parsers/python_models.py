# src/odoo_doctor/parsers/python_models.py
"""Parse Odoo Python models and controllers using stdlib ast."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from odoo_doctor.core.source import read_source


@dataclass
class FieldInfo:
    name: str
    field_type: str  # "Char", "Many2one", "Float", etc.
    comodel: str | None = None
    compute: str | None = None
    depends: list[str] = field(default_factory=list)
    store: bool = True


@dataclass
class MethodInfo:
    name: str
    decorators: list[str] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
    is_override: bool = False
    calls_super: bool = False
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


@dataclass
class ControllerInfo:
    method_name: str
    route: str
    auth: str = "user"
    uses_sudo: bool = False
    file_path: str = ""
    line: int = 0


# --- Odoo base class names ---
_MODEL_BASES = {"models.Model", "Model"}
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
}

_LIFECYCLE_METHODS = {"create", "write", "unlink", "default_get", "read", "copy"}


def parse_models(file_path: Path) -> list[ModelInfo]:
    """Parse all Odoo model classes from a Python file."""
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    models: list[ModelInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_odoo_model(node):
            continue
        models.append(_extract_model(node, str(file_path)))
    return models


def parse_controllers(file_path: Path) -> list[ControllerInfo]:
    """Parse all http.route controllers from a Python file."""
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    controllers: list[ControllerInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_info = _extract_route(item)
            if route_info is None:
                continue
            route, auth = route_info
            uses_sudo = _body_uses_sudo(item, source)
            controllers.append(
                ControllerInfo(
                    method_name=item.name,
                    route=route,
                    auth=auth,
                    uses_sudo=uses_sudo,
                    file_path=str(file_path),
                    line=item.lineno,
                )
            )
    return controllers


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
                    elif target.id == "_inherit":
                        model.inherit = _extract_inherit(item.value)
                    elif target.id == "_inherits" and isinstance(item.value, ast.Dict):
                        for k, v in zip(item.value.keys, item.value.values):
                            if isinstance(k, ast.Constant) and isinstance(
                                v, ast.Constant
                            ):
                                model.inherits[k.value] = v.value

        # Field definitions
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                field_info = _extract_field(target.id, item.value)
                if field_info:
                    model.fields[field_info.name] = field_info

        # Method definitions
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method = _extract_method(item)
            model.methods[method.name] = method

    return model


def _extract_inherit(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.List):
        return [
            e.value
            for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []


def _extract_field(name: str, call: ast.Call) -> FieldInfo | None:
    func_name = _dotted_name(call.func)
    if func_name is None:
        return None

    # Strip "fields." prefix
    short = func_name.split(".")[-1] if "." in func_name else func_name
    if short not in _ODOO_FIELD_TYPES:
        return None

    comodel = None
    compute = None
    depends: list[str] = []
    store = True

    # First positional arg for relational fields is comodel
    if call.args and isinstance(call.args[0], ast.Constant):
        if short in ("Many2one", "One2many", "Many2many"):
            comodel = call.args[0].value

    for kw in call.keywords:
        if kw.arg == "comodel_name" and isinstance(kw.value, ast.Constant):
            comodel = kw.value.value
        elif kw.arg == "compute" and isinstance(kw.value, ast.Constant):
            compute = kw.value.value
        elif kw.arg == "store" and isinstance(kw.value, ast.Constant):
            store = bool(kw.value.value)

    return FieldInfo(
        name=name,
        field_type=short,
        comodel=comodel,
        compute=compute,
        depends=depends,
        store=store if compute is None else store,
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
        line=func.lineno,
    )


def _body_calls_super(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "super"
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "super"
        ):
            return True
    return False


def _body_uses_sudo(func: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "sudo":
                return True
    return False


def _extract_route(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, str] | None:
    """Extract route and auth from @http.route decorator."""
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        dec_name = _dotted_name(dec.func)
        if dec_name not in ("http.route", "route"):
            continue
        route = ""
        auth = "user"
        if dec.args and isinstance(dec.args[0], ast.Constant):
            route = dec.args[0].value
        for kw in dec.keywords:
            if kw.arg == "auth" and isinstance(kw.value, ast.Constant):
                auth = kw.value.value
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
