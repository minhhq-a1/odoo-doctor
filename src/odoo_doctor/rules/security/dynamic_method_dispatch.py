# src/odoo_doctor/rules/security/dynamic_method_dispatch.py
"""Rule: dynamic-method-dispatch [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (*_FUNCTIONS, ast.Lambda, ast.ClassDef)
_GUARD_OPS = (ast.In, ast.NotIn, ast.Eq, ast.NotEq)


@rule(
    name="dynamic-method-dispatch",
    category="Security",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_dynamic_method_dispatch(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag ``getattr(obj, <name>)(...)`` where the code does not fix the name.

    Whoever controls the name can run any method of ``obj``, including the ORM's own
    (``unlink``, ``sudo``...). High confidence when the name comes from a parameter of a
    public method (reachable by RPC); medium for names read from records or other data,
    or in private helpers. A name checked in the same function (``in`` / ``==`` against
    something other than ``dir()``, ``startswith``) or built on a constant prefix
    (``'_get_%s' % kind``) is not reported.
    """
    if is_test_file(file_path, module_name):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    consts = _module_constants(tree)
    validators = _validators(tree)
    diags: list[Diagnostic] = []
    # (node, inside a function, names that are the parameter of an enclosing __getattr__)
    pending: list[tuple[ast.AST, bool, frozenset[str]]] = [(tree, False, frozenset())]
    while pending:
        node, in_function, hooks = pending.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FUNCTIONS):
                diags.extend(
                    _check_function(
                        child,
                        in_function,
                        consts,
                        validators,
                        hooks | _hook_names(child),
                        file_path,
                        module_name,
                        odoo_version,
                    )
                )
                pending.append((child, True, hooks | _hook_names(child)))
            else:
                pending.append((child, in_function, hooks))
    return sorted(diags, key=lambda d: (d.line, d.column))


def _own_nodes(fn: ast.AST):
    """Nodes of ``fn``'s body, without entering nested functions, lambdas or classes."""
    todo = list(ast.iter_child_nodes(fn))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, _SCOPES):
            todo.extend(ast.iter_child_nodes(node))


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


# str methods that hand back text derived from their receiver (or their arguments).
_TEXT_METHODS = {"strip", "lstrip", "rstrip", "lower", "upper", "title", "get", "pop"}
_TEXT_ARG_METHODS = {"replace", "format", "join"}
_LOGGER_NAMES = {"_logger", "logger", "log", "_log", "LOGGER", "_LOGGER"}


def _module_constants(tree: ast.Module) -> set[str]:
    """Names bound at module level: tables the code itself defines."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names |= {n for t in node.targets for n in _names(t)}
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            names |= _names(node.target)
    return names


def _client_value(node: ast.AST, tainted: set[str], consts: set[str]) -> bool:
    """True if the value is the caller's text, possibly reshaped (strip, key lookup...).

    Reading an attribute of a caller-supplied object gives stored data, not what the
    caller sent, and a lookup in a module-level table gives what the code defines.
    """
    if isinstance(node, ast.Name):
        return node.id in tainted and node.id not in consts
    if isinstance(node, ast.Subscript):
        return _client_value(node.value, tainted, consts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        attr = node.func.attr
        if attr in _TEXT_METHODS:
            return _client_value(node.func.value, tainted, consts)
        if attr in _TEXT_ARG_METHODS:
            return _client_value(node.func.value, tainted, consts) or any(
                _client_value(a, tainted, consts) for a in node.args
            )
        return False
    if isinstance(node, (ast.BinOp, ast.JoinedStr)):
        # Only a name made of the caller's text (and constants) is theirs to choose;
        # `prefix + self.state` mixes in stored data they do not control.
        parts = (
            [node.left, node.right]
            if isinstance(node, ast.BinOp)
            else [
                v.value if isinstance(v, ast.FormattedValue) else v for v in node.values
            ]
        )
        client = [_client_value(p, tainted, consts) for p in parts]
        fixed = [isinstance(p, ast.Constant) for p in parts]
        return any(client) and all(c or f for c, f in zip(client, fixed))
    if isinstance(node, ast.IfExp):
        return _client_value(node.body, tainted, consts) or _client_value(
            node.orelse, tainted, consts
        )
    if isinstance(node, ast.BoolOp):
        return any(_client_value(v, tainted, consts) for v in node.values)
    if isinstance(node, ast.Starred):
        return _client_value(node.value, tainted, consts)
    return False


def _tainted_names(fn, own: list[ast.AST], consts: set[str]) -> set[str]:
    """Parameters plus every local assigned (in a chain) from the caller's text."""
    args = fn.args
    params = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    params |= {a.arg for a in (args.vararg, args.kwarg) if a}
    tainted = params - {"self", "cls"}

    assigned: list[tuple[set[str], ast.AST]] = []
    for node in own:
        if isinstance(node, ast.Assign):
            targets = {n for t in node.targets for n in _names(t)}
            assigned.append((targets, node.value))
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
            if _client_value(value, tainted, consts) and not targets <= tainted:
                tainted |= targets
                changed = True
    return tainted


def _guarded_names(own: list[ast.AST], validators: set[str]) -> set[str]:
    """Names the function compares against something, tests with ``startswith`` or hands
    to a validator of this file."""
    guarded: set[str] = set()
    for node in own:
        if isinstance(node, ast.Compare) and all(
            isinstance(op, _GUARD_OPS) for op in node.ops
        ):
            operands = [node.left, *node.comparators]
            if any(_is_dir_call(o) for o in operands):
                continue  # `name in dir(obj)` only says the attribute exists
            for operand in operands:
                guarded |= _names(operand)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("startswith", "endswith")
        ):
            guarded |= _names(node.func.value)
        elif isinstance(node, ast.Call) and _called_name(node) in validators:
            for arg in node.args:
                guarded |= _names(arg)
    return guarded


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _hook_names(fn) -> frozenset[str]:
    """``name`` of ``def __getattr__(self, name)``: Python's attribute hook, not a client."""
    args = fn.args.args
    if fn.name in ("__getattr__", "__getattribute__") and len(args) >= 2:
        return frozenset({args[1].arg})
    return frozenset()


def _validators(tree: ast.Module) -> set[str]:
    """Functions of this file that refuse a parameter naming an ORM method.

    ``hasattr(models.BaseModel, name)`` is the test: it rejects ``unlink``, ``sudo``...
    shortcut: only the test is looked for, not what the function does with the answer.
    """
    found: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, _FUNCTIONS):
            continue
        params = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args)}
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "hasattr"
                and len(node.args) == 2
                and ast.unparse(node.args[0]).endswith("BaseModel")
                and isinstance(node.args[1], ast.Name)
                and node.args[1].id in params
            ):
                found.add(fn.name)
    return found


def _is_dir_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dir"
    )


def _has_constant_prefix(node: ast.expr) -> bool:
    """``f'_get_{x}'``, ``'_get_%s' % x``, ``'action_' + x``: confined to one family."""
    if isinstance(node, ast.JoinedStr):
        first = node.values[0] if node.values else None
        return isinstance(first, ast.Constant) and bool(first.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        left = node.left
        if isinstance(left, ast.Constant) and isinstance(left.value, str):
            return bool(left.value) and not left.value.startswith("%")
    return False


def _confined_variable(name_expr: ast.expr, own: list[ast.AST]) -> bool:
    """``name = f'_get_{x}'`` then ``getattr(obj, name)``: every assignment is prefixed."""
    if not isinstance(name_expr, ast.Name):
        return False
    values = [
        n.value
        for n in own
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name_expr.id for t in n.targets)
    ]
    return bool(values) and all(_has_constant_prefix(v) for v in values)


def _is_fixed_text(node: ast.expr) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)) or (
        _has_constant_prefix(node)
    )


def _fixed_names(own: list[ast.AST]) -> set[str]:
    """Locals only ever bound to something the code fixes.

    That is a function's own name (``origin.__name__``) or an item of a literal tuple
    / list of constant or constant-prefixed texts, directly or through a variable.
    shortcut: only plain assignments and ``for`` targets count as bindings.
    """
    values: dict[str, list[ast.AST | None]] = {}
    loops: list[tuple[str, ast.AST]] = []
    for node in own:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values.setdefault(target.id, []).append(node.value)
                else:
                    for name in _names(target):
                        values.setdefault(name, []).append(None)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            if isinstance(node.target, ast.Name):
                loops.append((node.target.id, node.iter))
            else:
                for name in _names(node.target):
                    values.setdefault(name, []).append(None)

    def literal_texts(node: ast.AST | None) -> bool:
        if isinstance(node, ast.Name):
            seen = values.get(node.id, [])
            return len(seen) == 1 and literal_texts(seen[0])
        return isinstance(node, (ast.Tuple, ast.List, ast.Set)) and all(
            _is_fixed_text(e) for e in node.elts
        )

    fixed = {
        name
        for name, seen in values.items()
        if all(isinstance(v, ast.Attribute) and v.attr == "__name__" for v in seen)
    }
    for name, iterable in loops:
        if name not in values and literal_texts(iterable):
            fixed.add(name)
    return fixed


def _is_logger(node: ast.expr) -> bool:
    """``_logger`` / ``self._logger``: picking a log level by name is harmless."""
    if isinstance(node, ast.Name):
        return node.id in _LOGGER_NAMES
    return isinstance(node, ast.Attribute) and node.attr in _LOGGER_NAMES


def _from_table(node: ast.expr, consts: set[str]) -> bool:
    """``TABLE[key]`` / ``TABLE.get(key)`` on a module-level name: the code fixes it."""
    if isinstance(node, ast.Subscript):
        return isinstance(node.value, ast.Name) and node.value.id in consts
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        value = node.func.value
        return (
            node.func.attr == "get"
            and isinstance(value, ast.Name)
            and value.id in consts
        )
    return False


def _is_getattr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    )


def _check_function(
    fn,
    nested: bool,
    consts: set[str],
    validators: set[str],
    hooks: frozenset[str],
    file_path: Path,
    module_name: str,
    odoo_version: str,
) -> list[Diagnostic]:
    own = list(_own_nodes(fn))
    candidates = [
        n
        for n in own
        if _is_getattr(n)
        and not isinstance(n.args[1], ast.Constant)
        and not _has_constant_prefix(n.args[1])
    ]
    if not candidates:
        return []

    parents: dict[int, ast.AST] = {}
    for node in [fn, *own]:
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    called_names = {
        n.func.id
        for n in own
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    tainted = _tainted_names(fn, own, consts)
    guarded = _guarded_names(own, validators)
    fixed = _fixed_names(own)
    entry = not nested and not fn.name.startswith("_")

    diags: list[Diagnostic] = []
    for call in candidates:
        parent = parents.get(id(call))
        invoked = isinstance(parent, ast.Call) and parent.func is call
        stored = (
            isinstance(parent, ast.Assign)
            and len(parent.targets) == 1
            and isinstance(parent.targets[0], ast.Name)
            and parent.targets[0].id in called_names
        )
        if not (invoked or stored):
            continue
        name_expr = call.args[1]
        if _is_logger(call.args[0]) or _from_table(name_expr, consts):
            continue
        if _confined_variable(name_expr, own):
            continue
        used = _names(name_expr)
        if used & guarded:
            continue
        if isinstance(name_expr, ast.Name) and name_expr.id in hooks:
            continue
        if used and used <= fixed:
            continue
        from_client = _client_value(name_expr, tainted, consts)
        confidence = "high" if entry and from_client else "medium"
        shown = ast.unparse(name_expr)
        shown = shown if len(shown) <= 50 else shown[:47] + "..."
        origin = (
            f"a parameter of public method '{fn.name}'"
            if confidence == "high"
            else "data the code does not fix"
        )
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=call.lineno,
                column=call.col_offset,
                rule="dynamic-method-dispatch",
                category="Security",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title="Method called by a name the code does not fix",
                message=(
                    f"getattr(..., {shown}) is called at line {call.lineno} and the "
                    f"name comes from {origin}: whoever sets it can run any method of "
                    "the object, ORM methods such as unlink() or sudo() included."
                ),
                help=(
                    "Map the accepted names to methods in a dict or a set and reject "
                    "the rest, or build the name on a constant prefix. Refusing names "
                    "that start with '_' is not enough."
                ),
                odoo_version=odoo_version,
            )
        )
    return diags
