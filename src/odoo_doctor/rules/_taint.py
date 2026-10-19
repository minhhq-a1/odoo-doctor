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
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import IntEnum


class Taint(IntEnum):
    SAFE = 0
    UNKNOWN = 1
    UNSAFE = 2


# Calls whose result cannot carry injected text.
_NUMERIC_CALLS = {"int", "float", "bool", "len", "abs", "round", "id", "ord", "hash"}
# Calls that return a date or time: it prints as digits, never as SQL.
_CLOCK_CALLS = {"now", "today", "utcnow"}
# Odoo `Query` (14-17): `get_sql()` returns the generated clauses, `select()` and
# `subselect()` the whole statement; only their arguments are text we pass in.
_QUERY_CALLS = {"select", "subselect"}
# Safe-by-construction SQL builders (Odoo `SQL`, psycopg2 `sql`, `quote_ident`).
_SAFE_BUILDERS = {"Identifier", "Literal", "Composed", "Placeholder", "quote_ident"}
# What a request carries: reading these is reading what the client sent.
_REQUEST_INPUT = {
    "params",
    "httprequest",
    "jsonrequest",
    "cookies",
    "session",
    "get_json_data",
    "get_http_params",
}
_REQUEST_NAMES = {"request", "http.request", "odoo.http.request"}
# Attributes of a record that describe it, not the data in its fields.
_RECORD_METADATA = {"env", "ids", "display_name", "pool"}
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

_trust_opaque: ContextVar[bool] = ContextVar("odoo_doctor_trust_opaque", default=False)


@contextmanager
def trusting_opaque_values() -> Iterator[None]:
    """Treat values the analysis cannot see into as constants, unless a variable fed them.

    Inside this block an attribute read, a call result or a name that is not bound here is
    ``UNKNOWN`` only when something it was built from is. What stays non-constant then comes
    from the function parameters the visitor hook :meth:`TaintVisitor.param_taint` marks.
    """
    token = _trust_opaque.set(True)
    try:
        yield
    finally:
        _trust_opaque.reset(token)


def _opaque(lookup: Lookup, *inputs: ast.expr) -> Taint:
    """State of a value we cannot see into, built from `inputs`."""
    if not _trust_opaque.get():
        return Taint.UNKNOWN
    unsafe = any(taint_of(i, lookup) != Taint.SAFE for i in inputs)
    return Taint.UNKNOWN if unsafe else Taint.SAFE


def _worst(*states: Taint) -> Taint:
    return max(states, default=Taint.SAFE)


def combine_add(left: Taint, right: Taint) -> Taint:
    """State of ``left + right`` / ``left += right`` on strings."""
    if left == Taint.SAFE and right == Taint.SAFE:
        return Taint.SAFE
    return Taint.UNSAFE


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else ""
    return ""


def _is_request_input(node: ast.expr) -> bool:
    """`request.params`, `http.request.httprequest`, `request.get_json_data`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr in _REQUEST_INPUT
        and _dotted(node.value) in _REQUEST_NAMES
    )


def _reads_own_field(node: ast.Attribute) -> bool:
    """`self.name`: a field of the record the method runs on (user-editable on a wizard)."""
    return (
        isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and not node.attr.startswith("_")
        and node.attr not in _RECORD_METADATA
    )


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
        # `_table` is set by the model's author; a record's `id` is an integer.
        if node.attr in {"_table", "id"}:
            return Taint.SAFE
        if _is_request_input(node):
            return Taint.UNKNOWN
        if _trust_opaque.get():
            if node.attr.startswith("_") or node.attr in _RECORD_METADATA:
                return Taint.SAFE
            if _reads_own_field(node):
                return Taint.UNKNOWN
        return _opaque(lookup, node.value)
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
    if isinstance(node, (ast.Starred, ast.NamedExpr)):
        return taint_of(node.value, lookup)
    return _opaque(lookup)


def _binop_taint(node: ast.BinOp, lookup: Lookup) -> Taint:
    if isinstance(node.op, ast.Add):
        return combine_add(taint_of(node.left, lookup), taint_of(node.right, lookup))
    if isinstance(node.op, ast.Mod):
        left = taint_of(node.left, lookup)
        args = node.right
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            states = _percent_text_args(node.left.value, args, lookup)
            if states is not None:
                return Taint.UNSAFE if any(s != Taint.SAFE for s in states) else left
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


# One `%` conversion of a printf-style template: `%s`, `%(key)d`, `%-5.2f`, `%%`.
_PERCENT_SPEC = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?(?P<conv>[a-zA-Z%])"
)
# `%d` of a string raises TypeError, so these conversions never write text.
_NUMERIC_CONVERSIONS = set("diouxXeEfFgG")


def _percent_text_args(
    template: str, args: ast.expr, lookup: Lookup
) -> list[Taint] | None:
    """States of the arguments a `%` template renders as text.

    Arguments bound to a numeric conversion are left out. None when the template
    cannot be paired with its arguments (`*` widths, a count mismatch, `*args`).
    """
    specs = [m for m in _PERCENT_SPEC.finditer(template) if m.group("conv") != "%"]
    if any("*" in m.group(0) for m in specs):
        return None
    keys = [m.group("key") for m in specs]
    if specs and all(k is not None for k in keys) and isinstance(args, ast.Dict):
        values = {
            k.value: v
            for k, v in zip(args.keys, args.values)
            if isinstance(k, ast.Constant)
        }
        if any(k not in values for k in keys):
            return None
        bound = [values[k] for k in keys]  # type: ignore[index]
    elif any(k is not None for k in keys):
        return None
    else:
        bound = list(args.elts) if isinstance(args, ast.Tuple) else [args]
        if len(bound) != len(specs) or any(isinstance(a, ast.Starred) for a in bound):
            return None
    return [
        taint_of(arg, lookup)
        for arg, spec in zip(bound, specs)
        if spec.group("conv") not in _NUMERIC_CONVERSIONS
    ]


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
    if _is_request_input(func):
        return Taint.UNKNOWN
    if name == "get_sql" and isinstance(func, ast.Attribute):
        return Taint.SAFE
    if name in _CLOCK_CALLS and isinstance(func, ast.Attribute):
        return Taint.SAFE
    if name in _QUERY_CALLS and isinstance(func, ast.Attribute):
        if all(taint_of(a, lookup) == Taint.SAFE for a in _call_inputs(node)):
            return Taint.SAFE
    if name == "SQL":
        # `SQL("... %s", x)` binds x; `SQL(f"...{x}")` just wraps an injected string.
        query = node.args[0] if node.args else None
        for kw in node.keywords:
            if kw.arg == "query":  # SQL(query=f"...")
                query = kw.value
        if query is not None and taint_of(query, lookup) == Taint.UNSAFE:
            return Taint.UNSAFE
        return Taint.SAFE
    if isinstance(func, ast.Name):
        if func.id in _NUMERIC_CALLS:
            return Taint.SAFE
        if func.id == "str" and node.args:
            return taint_of(node.args[0], lookup)
        return _opaque(lookup, *_call_inputs(node))
    if not isinstance(func, ast.Attribute):
        return _opaque(lookup, *_call_inputs(node))

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
    if _trust_opaque.get():
        if _reads_field_by_name(node, func):
            return Taint.UNKNOWN
        if func.attr.startswith("_"):  # a method of the model: only its arguments count
            return _opaque(lookup, *_call_inputs(node))
    return _opaque(lookup, func.value, *_call_inputs(node))


def _reads_field_by_name(node: ast.Call, func: ast.Attribute) -> bool:
    """`self.mapped("name")`: the values of a public field of the record."""
    return (
        func.attr == "mapped"
        and isinstance(func.value, ast.Name)
        and func.value.id == "self"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and not node.args[0].value.startswith("_")
        and node.args[0].value not in {"id", "ids", *_RECORD_METADATA}
    )


def _call_inputs(node: ast.Call) -> list[ast.expr]:
    return [*node.args, *(kw.value for kw in node.keywords)]


def _checked_choice(node: ast.If) -> str | None:
    """`x` after ``if x not in ("<", "="): return/raise``: it is one of those constants."""
    test = node.test
    if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.NotIn)
        and isinstance(test.comparators[0], (ast.Tuple, ast.List, ast.Set))
        and all(isinstance(e, ast.Constant) for e in test.comparators[0].elts)
        and not node.orelse
        and isinstance(node.body[-1], (ast.Return, ast.Raise))
    ):
        return None
    return test.left.id


class TaintVisitor(ast.NodeVisitor):
    """AST visitor that keeps a per-scope map of variable taint states."""

    def __init__(self) -> None:
        self._scopes: list[dict[str, Taint]] = [{}]

    # -- environment ---------------------------------------------------------

    def lookup(self, name: str) -> Taint:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return Taint.SAFE if _trust_opaque.get() else Taint.UNKNOWN

    def param_taint(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef, name: str
    ) -> Taint:
        """Hook: state of parameter `name` of `func` (default: an opaque value)."""
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
        scope = {a.arg: self.param_taint(node, a.arg) for a in params}
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                scope[extra.arg] = self.param_taint(node, extra.arg)
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

    def _pairs(
        self, target: ast.expr, value: ast.expr | None
    ) -> list[tuple[str, Taint]]:
        """(name, state) bindings of an assignment; a tuple target pairs up element-wise."""
        if isinstance(target, ast.Name):
            return [(target.id, self.taint(value) if value else Taint.UNKNOWN)]
        if not isinstance(target, (ast.Tuple, ast.List)):
            return []
        if value is not None and self.taint(value) == Taint.SAFE:
            # `a, b = <safe value>`: every part of a safe value is safe (`query.get_sql()`)
            return [
                (n.id, Taint.SAFE) for n in ast.walk(target) if isinstance(n, ast.Name)
            ]
        elts = target.elts
        paired = (
            isinstance(value, (ast.Tuple, ast.List))
            and len(value.elts) == len(elts)
            and not any(isinstance(e, ast.Starred) for e in (*elts, *value.elts))
        )
        values = value.elts if paired else [None] * len(elts)  # type: ignore[union-attr]
        return [p for e, v in zip(elts, values) for p in self._pairs(e, v)]

    def _bind(self, target: ast.expr, value: ast.expr | None) -> None:
        # Resolve every right-hand side first so `a, b = b, a` swaps correctly.
        for name, state in self._pairs(target, value):
            self._set(name, state)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._set(node.target.id, self.taint(node.value))

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
        checked = _checked_choice(node)
        if checked is not None:
            self._set(checked, Taint.SAFE)

    def visit_Try(self, node: ast.Try) -> None:
        self._branches([node.body + node.orelse, *(h.body for h in node.handlers)])
        for stmt in node.finalbody:
            self.visit(stmt)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def _loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        if not isinstance(node, ast.While):
            self.visit(node.iter)
            iter_state = self.taint(node.iter)
            if (
                _trust_opaque.get()
                and isinstance(node.iter, ast.Name)
                and node.iter.id == "self"
            ):
                iter_state = Taint.UNKNOWN  # `for rec in self`: rec.name is user data
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
                self._bind(item.optional_vars, item.context_expr)
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
