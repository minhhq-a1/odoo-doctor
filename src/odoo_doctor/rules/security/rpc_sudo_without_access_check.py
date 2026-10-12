# src/odoo_doctor/rules/security/rpc_sudo_without_access_check.py
"""Rule: rpc-sudo-without-access-check [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.parsers.python_models import (
    _body_checks_access,
    _extract_route,
    _is_constant_config_read,
)
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (*_FUNCTIONS, ast.Lambda, ast.ClassDef)

_MODEL_BASES = {"Model", "TransientModel", "AbstractModel"}
# ORM entry points the client reaches by name; their sudo() is the framework's business.
_ORM_OVERRIDES = {
    "create", "write", "unlink", "read", "copy", "copy_data", "browse", "search",
    "search_read", "search_fetch", "search_count", "read_group", "web_read",
    "web_search_read", "web_save", "name_search", "name_create", "default_get",
    "fields_get", "get_view", "onchange", "check_access", "check_access_rights",
    "check_access_rule", "has_access", "exists", "ensure_one", "filtered", "mapped",
}  # fmt: skip
_NOT_ENTRY_DECORATORS = {
    "api.depends", "api.constrains", "api.onchange", "api.private", "api.autovacuum",
    "api.depends_context", "api.ondelete", "property", "staticmethod", "classmethod",
}  # fmt: skip
# Calls that read or change records.
_ORM_CALLS = {
    "browse", "search", "search_read", "search_fetch", "search_count", "read",
    "read_group", "write", "unlink", "create", "copy", "exists", "filtered_domain",
}  # fmt: skip
# Calls that change records; a state-changing button method counts too.
_MUTATIONS = {
    "write",
    "unlink",
    "create",
    "action_archive",
    "action_unarchive",
    "toggle_active",
}
# Other ways a method shows it restricted the caller.
_EXTRA_CHECKS = {
    "has_access", "has_group", "user_has_groups", "is_admin", "is_system",
}  # fmt: skip


@rule(
    name="rpc-sudo-without-access-check",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_rpc_sudo_without_access_check(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag public methods that elevate with ``sudo()`` on records the caller picked.

    A public model method (or an authenticated route) is reachable with any record ids
    and arguments. When one of its parameters reaches an ORM call on a ``sudo()``
    recordset and nothing in the method checks the caller's access (``check_access``,
    ``has_access``, a token, a group test), the caller can read or change records they
    cannot see. High confidence when the parameter reaches the elevated recordset itself;
    medium when the method elevates and also uses a parameter on the ORM elsewhere. Public
    routes are left to ``public-controller-sudo-risk``.
    """
    if is_test_file(file_path, module_name):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        kind = _class_kind(cls)
        if kind is None:
            continue
        for fn in cls.body:
            if isinstance(fn, _FUNCTIONS) and _is_entry(fn, kind):
                diag = _check_function(fn, file_path, module_name, odoo_version)
                if diag is not None:
                    diags.append(diag)
    return sorted(diags, key=lambda d: d.line)


def _class_kind(cls: ast.ClassDef) -> str | None:
    for base in cls.bases:
        text = ast.unparse(base)
        if text.rsplit(".", 1)[-1] in _MODEL_BASES:
            return "model"
        if text.rsplit(".", 1)[-1] == "Controller":
            return "controller"
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("_name", "_inherit")
            for t in node.targets
        ):
            return "model"
    return None


def _is_entry(fn, kind: str) -> bool:
    if kind == "controller":
        route = _extract_route(fn)
        return route is not None and route[1] not in ("public", "none")
    if fn.name.startswith("_") or fn.name in _ORM_OVERRIDES:
        return False
    decorators = {ast.unparse(d).split("(")[0] for d in fn.decorator_list}
    return not decorators & _NOT_ENTRY_DECORATORS


def _own_nodes(fn):
    todo = list(ast.iter_child_nodes(fn))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, _SCOPES):
            todo.extend(ast.iter_child_nodes(node))


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _tainted(fn, own: list[ast.AST]) -> set[str]:
    """Parameters plus locals derived from them in any way."""
    args = fn.args
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    names |= {a.arg for a in (args.vararg, args.kwarg) if a}
    tainted = names - {"self", "cls"}
    assigned: list[tuple[set[str], ast.AST]] = []
    for node in own:
        if isinstance(node, ast.Assign):
            assigned.append(({n for t in node.targets for n in _names(t)}, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value:
            assigned.append((_names(node.target), node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            assigned.append((_names(node.target), node.iter))
        elif isinstance(node, ast.NamedExpr):
            assigned.append((_names(node.target), node.value))
    changed = True
    while changed:
        changed = False
        for targets, value in assigned:
            if _filtered_by_caller(value) and not _is_elevated(value):
                continue
            if _names(value) & tainted and not targets <= tainted:
                tainted |= targets
                changed = True
    return tainted


def _elevations(own: list[ast.AST], parents: dict[ast.AST, ast.AST]) -> list[ast.Call]:
    """``.sudo()`` calls that raise privileges (not ``sudo(False)``, not a config read)."""
    found = []
    for node in own:
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sudo"
        ):
            continue
        values = [*node.args[:1], *(k.value for k in node.keywords)]
        if any(isinstance(v, ast.Constant) and v.value is False for v in values):
            continue
        if _is_constant_config_read(node, parents):
            continue
        found.append(node)
    return sorted(found, key=lambda n: (n.lineno, n.col_offset))


def _chain_calls_above(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> list[ast.Call]:
    """Calls whose receiver chain runs through ``node`` (``x.sudo().browse(a).read()``)."""
    calls: list[ast.Call] = []
    current = node
    while True:
        parent = parents.get(current)
        if isinstance(parent, ast.Attribute) and parent.value is current:
            current = parent
        elif isinstance(parent, ast.Call) and parent.func is current:
            calls.append(parent)
            current = parent
        elif isinstance(parent, ast.Subscript) and parent.value is current:
            current = parent
        else:
            return calls


def _root_name(node: ast.AST) -> str | None:
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            return None


# Calls that only reshape a value or walk the ORM: not a place a check could hide.
_PLAIN_CALLS = _ORM_CALLS | {
    "sudo", "with_context", "with_user", "with_company", "with_env", "get", "pop",
    "int", "str", "float", "bool", "len", "list", "tuple", "set", "dict", "sorted",
    "isinstance", "any", "all", "min", "max", "sum", "map", "filter", "range", "zip",
    "enumerate", "format", "join", "strip", "lower", "upper", "split", "append",
    "extend", "update", "items", "keys", "values", "mapped", "filtered", "ids", "ensure_one", "_", "json", "dumps", "loads", "isdigit", "startswith",
    "endswith", "replace", "decode", "encode", "literal_eval", "safe_eval",
}  # fmt: skip


# Fragments of names of calls that restrict who may proceed (beyond the parser's own list).
_CHECK_FRAGMENTS = (
    "can_", "allowed", "permission", "authoriz", "access", "owner", "ownership",
    "check", "verify", "validate",
)  # fmt: skip
_NOT_A_CHECK = ("generate", "_generate", "compute", "_compute", "get_access", "grant")
# Exceptions a method raises to refuse the caller.
_REFUSALS = {"AccessError", "AccessDenied", "Forbidden", "Unauthorized", "NotFound"}


def _restricts_caller(own: list[ast.AST]) -> bool:
    """A check-style call, or a ``raise`` that refuses the caller, is in the method."""
    for node in own:
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if ast.unparse(target).rsplit(".", 1)[-1] in _REFUSALS:
                return True
        elif isinstance(node, ast.Call):
            name = _called_name(node).lstrip("_").lower()
            if (
                name
                and not name.startswith(_NOT_A_CHECK)
                and any(f in name for f in _CHECK_FRAGMENTS)
            ):
                return True
    return False


def _mentions_caller(own: list[ast.AST]) -> bool:
    """``env.user`` / ``env.uid`` / ``request.uid``: the method probably scopes by caller."""
    for node in own:
        if isinstance(node, ast.Attribute) and node.attr in ("user", "uid"):
            if _root_name(node.value) in ("self", "request", "env", "cls"):
                return True
            if isinstance(node.value, ast.Attribute) and node.value.attr == "env":
                return True
    return False


# search runs with the caller's rights, so its result is already limited to what they see.
_SEARCH_CALLS = {"search", "search_read", "search_fetch", "search_count", "read_group"}


def _is_elevated(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "sudo"
        for n in ast.walk(node)
    )


def _filtered_by_caller(expr: ast.AST) -> bool:
    """The expression runs a ``search`` that is not itself elevated."""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in _SEARCH_CALLS
        and not _is_elevated(n.func.value)
        for n in ast.walk(expr)
    )


def _refuses_by_owner_compare(own: list[ast.AST], sudo_vars: set[str]) -> bool:
    """``if rec.owner_id not in mine: return/raise``: the record is tied to the caller."""
    for node in own:
        if not isinstance(node, ast.If):
            continue
        if not any(
            isinstance(n, (ast.Return, ast.Raise))
            for b in node.body
            for n in ast.walk(b)
        ):
            continue
        for cmp in (n for n in ast.walk(node.test) if isinstance(n, ast.Compare)):
            if not all(
                isinstance(op, (ast.In, ast.NotIn, ast.Eq, ast.NotEq)) for op in cmp.ops
            ):
                continue
            sides = [cmp.left, *cmp.comparators]
            owned = any(
                isinstance(x, ast.Attribute) and _root_name(x) in sudo_vars
                for x in sides
            )
            other = any(
                not isinstance(x, ast.Constant)
                and not (isinstance(x, ast.Attribute) and _root_name(x) in sudo_vars)
                for x in sides
            )
            if owned and other:
                return True
    return False


def _delegates(own: list[ast.AST], tainted: set[str]) -> bool:
    """A parameter is handed to another method or function, where a check may live."""
    for node in own:
        if not isinstance(node, ast.Call) or _called_name(node) in _PLAIN_CALLS:
            continue
        if _args_names(node) & tainted:
            return True
    return False


def _chain_reaches(call: ast.Call, tainted: set[str]) -> bool:
    """Does the caller's value reach this call, through its arguments or its receiver?

    A receiver that went through the caller's own ``search`` is already filtered.
    """
    if _args_names(call) & tainted:
        return True
    return bool(_names(call.func) & tainted and not _filtered_by_caller(call.func))


def _args_names(call: ast.Call) -> set[str]:
    names: set[str] = set()
    for arg in (*call.args, *(k.value for k in call.keywords)):
        if isinstance(arg, ast.Dict) and all(
            isinstance(k, ast.Constant) for k in arg.keys
        ):
            continue  # keys fixed by the code: values are data, not a mass assignment
        names |= _names(arg)
    return names


def _check_function(fn, file_path: Path, module_name: str, odoo_version: str):
    own = list(_own_nodes(fn))
    parents: dict[ast.AST, ast.AST] = {}
    for node in [fn, *own]:
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    elevations = _elevations(own, parents)
    if not elevations:
        return None
    if (
        _body_checks_access(fn)
        or _restricts_caller(own)
        or any(
            isinstance(n, ast.Call) and _called_name(n) in _EXTRA_CHECKS for n in own
        )
    ):
        return None

    tainted = _tainted(fn, own)
    if not tainted or _delegates(own, tainted):
        return None

    sudo_vars: set[str] = set()
    for node in own:
        if isinstance(node, ast.Assign) and any(
            e in ast.walk(node.value) for e in elevations
        ):
            sudo_vars |= {n for t in node.targets for n in _names(t)}

    if _refuses_by_owner_compare(own, sudo_vars):
        return None

    def mutating(call: ast.Call) -> bool:
        name = _called_name(call)
        return name in _MUTATIONS or name.startswith(("action_", "button_"))

    high = False
    for sudo in elevations:
        above = _chain_calls_above(sudo, parents)
        receiver = sudo.func.value  # type: ignore[attr-defined]
        if (
            _names(receiver) & tainted
            and not _filtered_by_caller(receiver)
            and any(mutating(c) for c in above)
        ):
            high = True
        if any(mutating(c) and _chain_reaches(c, tainted) for c in above):
            high = True
    for node in own:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _root_name(node.func.value) in sudo_vars
            and mutating(node)
            and (_args_names(node) & tainted or _names(node.func.value) & tainted)
        ):
            high = True
    reads_chosen = any(
        _args_names(c) & tainted
        for s in elevations
        for c in _chain_calls_above(s, parents)
    ) or any(
        _names(s.func.value) & tainted  # type: ignore[attr-defined]
        and not _filtered_by_caller(s.func.value)  # type: ignore[attr-defined]
        for s in elevations
    )

    reaches_orm = reads_chosen or any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in _ORM_CALLS
        and not (
            n.func.attr in _SEARCH_CALLS
            and not _is_elevated(n.func.value)
            and _root_name(n.func.value) not in sudo_vars
        )
        and _args_names(n) & tainted
        for n in own
    )
    if not (high or reaches_orm):
        return None

    first = elevations[0]
    confidence = "high" if high and not _mentions_caller(own) else "medium"
    return Diagnostic(
        module=module_name,
        file_path=str(file_path),
        line=first.lineno,
        column=first.col_offset,
        rule="rpc-sudo-without-access-check",
        category="Security",
        severity="error",
        tier="P1",
        source="native",
        confidence=confidence,
        title=f"Public method '{fn.name}' elevates with sudo() and checks no access",
        message=(
            f"'{fn.name}' is reachable with any record ids and arguments and calls "
            f".sudo() at line {first.lineno}"
            + (
                " on records chosen by its parameters"
                if high
                else ", while a parameter also reaches the ORM"
            )
            + ", with no access check (check_access, has_access, a token or a group "
            "test) in the method: a caller can read or change records they cannot see."
        ),
        help=(
            "Check the caller's rights on the records before elevating "
            "(record.check_access('read') / has_access), or drop sudo() and let the "
            "record rules apply; elevate only the narrowest recordset and return "
            "only the fields the caller may see."
        ),
        odoo_version=odoo_version,
    )
