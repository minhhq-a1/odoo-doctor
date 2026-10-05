# src/odoo_doctor/rules/_taint.py
"""Small intra-procedural taint analysis shared by the Security rules.

Every expression gets one of three states:

* ``SAFE``    - provably built from constants only (string literals, ``int()`` casts,
  ``','.join(['%s'] * n)`` placeholder lists, ``self._table``, ``SQL(...)``, ...).
* ``UNKNOWN`` - an opaque value: a function parameter, an attribute read, the result
  of an arbitrary call. Passing it around is not a finding by itself.
* ``UNSAFE``  - a string *constructed* by interpolating/concatenating something that
  is not ``SAFE`` (f-string, ``%``, ``.format``, ``+``, ``join``).

States are followed through local variables, lists (``append``/``extend``/``+=``),
``if``/``try``/loop branches (worst case wins) and module-level constants. Rules
subclass :class:`TaintVisitor` and implement :meth:`check_call` to examine sinks.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from enum import IntEnum


class Taint(IntEnum):
    SAFE = 0
    UNKNOWN = 1
    UNSAFE = 2


# Calls whose result cannot carry injected text.
_NUMERIC_CALLS = {"int", "float", "bool", "len", "abs", "round", "id", "ord", "hash"}
# Safe-by-construction SQL builders (Odoo `SQL`, psycopg2 `sql`, `quote_ident`).
_SAFE_BUILDERS = {"SQL", "Identifier", "Literal", "Composed", "quote_ident"}
# str methods that only reshape their receiver; arguments can still inject text.
_STR_METHODS = {
    "strip",
    "lstrip",
    "rstrip",
    "lower",
    "upper",
    "title",
    "capitalize",
    "replace",
    "encode",
    "decode",
}

Lookup = Callable[[str], Taint]


def _worst(*states: Taint) -> Taint:
    return max(states, default=Taint.SAFE)


def combine_add(left: Taint, right: Taint) -> Taint:
    """State of ``left + right`` / ``left += right`` on strings."""
    if left == Taint.SAFE and right == Taint.SAFE:
        return Taint.SAFE
    return Taint.UNSAFE


def _builder_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def taint_of(node: ast.expr, lookup: Lookup) -> Taint:
    """Taint state of an expression; `lookup` resolves bare names."""
    if isinstance(node, ast.Constant):
        return Taint.SAFE
    if isinstance(node, ast.Name):
        return lookup(node.id)
    if isinstance(node, ast.Attribute):
        if (
            node.attr == "_table"
            and isinstance(node.value, ast.Name)
            and node.value.id in {"self", "cls"}
        ):
            return Taint.SAFE
        return Taint.UNKNOWN
    if isinstance(node, ast.JoinedStr):
        parts = [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
        if all(taint_of(p, lookup) == Taint.SAFE for p in parts):
            return Taint.SAFE
        return Taint.UNSAFE
    if isinstance(node, ast.BinOp):
        return _binop_taint(node, lookup)
    if isinstance(node, ast.Call):
        return _call_taint(node, lookup)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return _worst(*(taint_of(e, lookup) for e in node.elts))
    if isinstance(node, ast.Dict):
        return _worst(*(taint_of(v, lookup) for v in node.values if v is not None))
    if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        return _comprehension_taint(node, lookup)
    if isinstance(node, ast.IfExp):
        return _worst(taint_of(node.body, lookup), taint_of(node.orelse, lookup))
    if isinstance(node, ast.BoolOp):
        return _worst(*(taint_of(v, lookup) for v in node.values))
    if isinstance(node, ast.Subscript):
        return (
            Taint.SAFE if taint_of(node.value, lookup) == Taint.SAFE else Taint.UNKNOWN
        )
    if isinstance(node, ast.Starred):
        return taint_of(node.value, lookup)
    return Taint.UNKNOWN


def _binop_taint(node: ast.BinOp, lookup: Lookup) -> Taint:
    if isinstance(node.op, ast.Add):
        return combine_add(taint_of(node.left, lookup), taint_of(node.right, lookup))
    if isinstance(node.op, ast.Mod):
        left = taint_of(node.left, lookup)
        args = node.right
        if isinstance(args, (ast.Tuple, ast.List)):
            arg_states = [taint_of(e, lookup) for e in args.elts]
        elif isinstance(args, ast.Dict):
            arg_states = [taint_of(v, lookup) for v in args.values if v is not None]
        else:
            arg_states = [taint_of(args, lookup)]
        if any(s != Taint.SAFE for s in arg_states) or left == Taint.UNSAFE:
            return Taint.UNSAFE
        return left
    if isinstance(node.op, ast.Mult):
        # `["%s"] * n`: the multiplier is a number, only the sequence carries text.
        for side in (node.left, node.right):
            if isinstance(side, (ast.List, ast.Tuple)) or (
                isinstance(side, ast.Constant) and isinstance(side.value, str)
            ):
                return taint_of(side, lookup)
        return _worst(taint_of(node.left, lookup), taint_of(node.right, lookup))
    return Taint.UNKNOWN


def _comprehension_taint(node: ast.expr, lookup: Lookup) -> Taint:
    bound: dict[str, Taint] = {}

    def scoped(name: str) -> Taint:
        return bound[name] if name in bound else lookup(name)

    for gen in node.generators:  # type: ignore[attr-defined]
        iter_state = taint_of(gen.iter, scoped)
        for target in ast.walk(gen.target):
            if isinstance(target, ast.Name):
                bound[target.id] = (
                    Taint.SAFE if iter_state == Taint.SAFE else Taint.UNKNOWN
                )
    return taint_of(node.elt, scoped)  # type: ignore[attr-defined]


def elements_taint(node: ast.expr, lookup: Lookup) -> Taint:
    """State of the items of an iterable expression (what `str.join` would glue)."""
    return taint_of(node, lookup)


def _call_taint(node: ast.Call, lookup: Lookup) -> Taint:
    func = node.func
    name = _builder_name(func)
    if name in _SAFE_BUILDERS:
        return Taint.SAFE
    if isinstance(func, ast.Name):
        if func.id in _NUMERIC_CALLS:
            return Taint.SAFE
        if func.id == "str" and node.args:
            return taint_of(node.args[0], lookup)
        return Taint.UNKNOWN
    if not isinstance(func, ast.Attribute):
        return Taint.UNKNOWN

    receiver = taint_of(func.value, lookup)
    arg_states = [taint_of(a, lookup) for a in node.args] + [
        taint_of(kw.value, lookup) for kw in node.keywords
    ]
    if func.attr == "join" and node.args:
        items = elements_taint(node.args[0], lookup)
        if receiver == Taint.UNSAFE or items == Taint.UNSAFE:
            return Taint.UNSAFE
        if receiver == Taint.SAFE and items == Taint.SAFE:
            return Taint.SAFE
        return Taint.UNKNOWN
    if func.attr == "format":
        if receiver == Taint.UNSAFE or any(s != Taint.SAFE for s in arg_states):
            return Taint.UNSAFE
        return receiver
    if func.attr in _STR_METHODS:
        if any(s != Taint.SAFE for s in arg_states):
            return Taint.UNSAFE
        return receiver
    return Taint.UNKNOWN


class TaintVisitor(ast.NodeVisitor):
    """AST visitor that keeps a per-scope map of variable taint states."""

    def __init__(self) -> None:
        self._scopes: list[dict[str, Taint]] = [{}]

    # -- environment ---------------------------------------------------------

    def lookup(self, name: str) -> Taint:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return Taint.UNKNOWN

    def taint(self, node: ast.expr) -> Taint:
        return taint_of(node, self.lookup)

    def _set(self, name: str, state: Taint) -> None:
        self._scopes[-1][name] = state

    def _raise(self, name: str, state: Taint) -> None:
        """Weaken a (possibly outer-scope) variable after a mutation like append."""
        for scope in reversed(self._scopes):
            if name in scope:
                scope[name] = _worst(scope[name], state)
                return
        self._scopes[-1][name] = _worst(Taint.UNKNOWN, state)

    def _snapshot(self) -> list[dict[str, Taint]]:
        return [dict(s) for s in self._scopes]

    def _branches(self, blocks: list[list[ast.stmt]]) -> None:
        """Visit alternative blocks from the same start state; keep the worst."""
        start = self._snapshot()
        results: list[list[dict[str, Taint]]] = []
        for block in blocks:
            self._scopes = [dict(s) for s in start]
            for stmt in block:
                self.visit(stmt)
            results.append(self._scopes)
        # Every result already contains the pre-branch values, so merge over the
        # results only: a variable reassigned in all branches forgets its old state.
        merged: list[dict[str, Taint]] = [{} for _ in start]
        for result in results:
            for depth, scope in enumerate(result):
                for name, state in scope.items():
                    merged[depth][name] = (
                        _worst(merged[depth][name], state)
                        if name in merged[depth]
                        else state
                    )
        self._scopes = merged

    # -- sinks (override) ----------------------------------------------------

    def check_call(self, node: ast.Call) -> None:
        """Hook: examine a call with the current variable states."""

    # -- statements ----------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        # Module constants are visible to every function, wherever they are defined.
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self._set(target.id, self.taint(stmt.value))
        for stmt in node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = node.args
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        scope = {a.arg: Taint.UNKNOWN for a in params}
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                scope[extra.arg] = Taint.UNKNOWN
        self._scopes.append(scope)
        for stmt in node.body:
            self.visit(stmt)
        self._scopes.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scopes.append({})
        for stmt in node.body:
            self.visit(stmt)
        self._scopes.pop()

    def _bind(self, target: ast.expr, value: ast.expr | None) -> None:
        if isinstance(target, ast.Name):
            self._set(
                target.id, self.taint(value) if value is not None else Taint.UNKNOWN
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind(elt, None)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._bind(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            self._bind(node.target, node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name) and isinstance(node.op, ast.Add):
            old = self.lookup(node.target.id)
            if isinstance(node.value, (ast.List, ast.Tuple, ast.ListComp)):
                self._set(node.target.id, _worst(old, self.taint(node.value)))
            else:
                self._set(node.target.id, combine_add(old, self.taint(node.value)))
        elif isinstance(node.target, ast.Name):
            self._set(node.target.id, Taint.UNKNOWN)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        self._branches([node.body, node.orelse])

    def visit_Try(self, node: ast.Try) -> None:
        self._branches([node.body + node.orelse, *(h.body for h in node.handlers)])
        for stmt in node.finalbody:
            self.visit(stmt)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def _loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        if not isinstance(node, ast.While):
            self.visit(node.iter)
            iter_state = self.taint(node.iter)
            for target in ast.walk(node.target):
                if isinstance(target, ast.Name):
                    self._set(
                        target.id,
                        Taint.SAFE if iter_state == Taint.SAFE else Taint.UNKNOWN,
                    )
        else:
            self.visit(node.test)
        self._branches([node.body, []])
        for stmt in node.orelse:
            self.visit(stmt)

    visit_For = visit_AsyncFor = visit_While = _loop  # type: ignore[assignment]

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind(item.optional_vars, None)
        for stmt in node.body:
            self.visit(stmt)

    visit_AsyncWith = visit_With  # type: ignore[assignment]

    # -- calls ---------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        self._track_mutation(node)
        self.check_call(node)
        self.generic_visit(node)

    def _track_mutation(self, node: ast.Call) -> None:
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            return
        name = func.value.id
        if func.attr in {"append", "add"} and node.args:
            self._raise(name, self.taint(node.args[0]))
        elif func.attr in {"extend", "update"} and node.args:
            self._raise(name, elements_taint(node.args[0], self.lookup))
        elif func.attr == "insert" and len(node.args) >= 2:
            self._raise(name, self.taint(node.args[1]))
