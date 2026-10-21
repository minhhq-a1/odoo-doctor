# src/odoo_doctor/rules/_ast_helpers.py
"""Shared AST helper functions for rules."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path


def node_is_orm(
    node: ast.AST,
    orm_vars: set[str] | None = None,
    plain_attrs: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Check if an AST node evaluates to an ORM object.

    ``plain_attrs`` names attributes of ``self`` that hold ordinary Python objects
    (``self.client``): a chain that goes through one is not a recordset.
    """
    has_env_subscript = [False]
    root_name = [None]
    plain = [False]

    def check_node(n: ast.AST) -> None:
        if isinstance(n, ast.Name):
            root_name[0] = n.id
        elif isinstance(n, ast.Attribute):
            if (
                isinstance(n.value, ast.Name)
                and n.value.id in ("self", "cls")
                and n.attr in plain_attrs
            ):
                plain[0] = True
            check_node(n.value)
        elif isinstance(n, ast.Subscript):
            sub_val = n.value
            is_env = False
            if (
                isinstance(sub_val, ast.Name)
                and sub_val.id == "env"
                or isinstance(sub_val, ast.Attribute)
                and sub_val.attr == "env"
            ):
                is_env = True
            if is_env:
                has_env_subscript[0] = True
            check_node(sub_val)
        elif isinstance(n, ast.Call):
            check_node(n.func)

    check_node(node)

    if plain[0] and not has_env_subscript[0]:
        return False
    if root_name[0] in ("self", "cls"):
        return True
    if has_env_subscript[0]:
        return True
    if orm_vars and root_name[0] in orm_vars:
        return True

    return False


def receiver_is_orm(
    call: ast.Call,
    orm_vars: set[str] | None = None,
    plain_attrs: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Check if the receiver of a method call is likely an ORM object."""
    if not isinstance(call.func, ast.Attribute):
        return False
    return node_is_orm(call.func.value, orm_vars, plain_attrs)


def _path_below_addon(file_path: Path | str, module_name: str) -> tuple[str, ...]:
    """Path components below the addon directory (the last two if it is not on the path)."""
    parts = Path(file_path).parts
    if module_name in parts:
        return parts[len(parts) - parts[::-1].index(module_name) :]
    return parts[-2:]


def is_test_file(file_path: Path | str, module_name: str) -> bool:
    """True if the file sits in a `tests/` directory *inside* the addon.

    Only path components below the addon directory count, so an addon that lives
    under some unrelated `tests/` folder is not mistaken for test code.
    """
    return "tests" in _path_below_addon(file_path, module_name)[:-1]


def is_migration_file(file_path: Path | str, module_name: str) -> bool:
    """True for a script in the addon's `migrations/` directory.

    Those scripts run against databases of the version being left, so APIs removed in
    the new version are legitimate there.
    """
    return "migrations" in _path_below_addon(file_path, module_name)[:-1]


Comprehension = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp
LoopNode = ast.For | ast.While | Comprehension


def per_iteration_nodes(loop: LoopNode) -> Iterator[ast.AST]:
    """Nodes that run on every iteration of *loop*.

    That is its body (and, for a ``while``, its condition). For a comprehension it is the
    element, the conditions and the iterables after the first. The iterable of a ``for``
    (the first one of a comprehension) and its ``else`` clause run once, so they are not
    in the loop. A nested loop is the business of its own check, except that its
    iterable and ``else`` clause run once per iteration of this one and are yielded here.
    """
    if isinstance(loop, (ast.For, ast.While)):
        todo: deque[ast.AST] = deque(loop.body)
    else:
        gens = loop.generators
        todo = deque(
            [loop.key, loop.value] if isinstance(loop, ast.DictComp) else [loop.elt]
        )
        todo.extend(i for g in gens for i in g.ifs)
        todo.extend(g.iter for g in gens[1:])
    if isinstance(loop, ast.While):
        todo.appendleft(loop.test)
    while todo:
        curr = todo.popleft()
        yield curr
        if isinstance(curr, (ast.For, ast.While)):
            if isinstance(curr, ast.For):
                todo.append(curr.iter)
            todo.extend(curr.orelse)
        else:
            todo.extend(ast.iter_child_nodes(curr))


def is_bounded_loop(loop: LoopNode) -> bool:
    """A ``for`` whose iteration count does not scale with the data.

    Loops over chunks (``split_every(...)``, ``range(start, stop, step)``) run once per
    chunk, which is the remedy for a per-record call, and a loop over a literal tuple /
    list of constants is bounded by the source code. A comprehension counts by its
    first iterable.
    """
    if isinstance(loop, ast.While):
        return False
    it = loop.iter if isinstance(loop, ast.For) else loop.generators[0].iter
    if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
        return all(isinstance(e, ast.Constant) for e in it.elts)
    if isinstance(it, ast.Call):
        name = (
            it.func.id
            if isinstance(it.func, ast.Name)
            else it.func.attr
            if isinstance(it.func, ast.Attribute)
            else None
        )
        if name == "split_every":
            return True
        if name == "range" and len(it.args) == 3:
            return True
    return False


# Calls whose result is plain data, not a recordset: a local bound to one is not iterated
# as records.
_PLAIN_DATA_METHODS = {
    "search_count",
    "read",
    "search_read",
    "read_group",
    "_read_group",
}


def _is_field_declaration(value: ast.expr) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "fields"
    )


def plain_self_attrs(cls: ast.ClassDef) -> set[str]:
    """Attributes of ``self`` that hold ordinary Python objects, not records or fields.

    Those set in ``__init__`` (``self.client = client``) and those the class body
    assigns something other than a ``fields.X(...)`` declaration. A recordset gets its
    attributes from fields, so ``self.client.search(...)`` on a service object is not an
    ORM query.

    shortcut: an attribute inherited from a plain Python base is not known, when the
    base class could be resolved.
    """
    attrs: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and not _is_field_declaration(stmt.value):
            attrs.update(
                t.id
                for t in stmt.targets
                if isinstance(t, ast.Name) and not t.id.startswith("_")
            )
        elif isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
            for n in ast.walk(stmt):
                targets = n.targets if isinstance(n, ast.Assign) else []
                if isinstance(n, ast.AnnAssign):
                    targets = [n.target]
                attrs.update(
                    t.attr
                    for t in targets
                    if isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                )
    return attrs


def _root_name(node: ast.AST) -> str | None:
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            return None


def _bind_loop_targets(
    loop: LoopNode,
    orm_vars: set[str],
    inferred: set[str],
    plain: frozenset[str] | set[str],
) -> None:
    """The loop variable of a loop over records is itself a record."""
    if isinstance(loop, ast.While):
        return
    pairs = (
        [(loop.target, loop.iter)]
        if isinstance(loop, ast.For)
        else [(g.target, g.iter) for g in loop.generators]
    )
    for target, it in pairs:
        if node_is_orm(it, orm_vars, plain):
            names = {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
            orm_vars.update(names)
            if _root_name(it) in inferred:
                inferred.update(names)
            else:
                inferred.difference_update(names)


_RECORDSET_METHODS = {
    "search",
    "browse",
    "mapped",
    "filtered",
    "filtered_domain",
    "sorted",
    "sudo",
    "with_context",
    "with_company",
    "with_user",
    "with_env",
    "exists",
    "concat",
    "grouped",
}


def _clearly_records(value: ast.expr, orm_vars: set[str]) -> bool:
    """``self.env['x']...``, a recordset method on anything ORM, or a known recordset name;
    not ``self._get_regex()`` (any other call on ``self``)."""
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        if value.func.attr in _RECORDSET_METHODS:
            return True
    return any(isinstance(n, ast.Subscript) for n in ast.walk(value)) or _root_name(
        value
    ) in orm_vars | {"cls"} - {"self"}


def _bind_assign(
    node: ast.Assign,
    orm_vars: set[str],
    inferred: set[str],
    plain: frozenset[str] | set[str],
) -> None:
    """``recs = self.env['x'].search([])`` makes ``recs`` a recordset for what follows."""
    value = node.value
    plain_data = (
        isinstance(value, ast.Attribute)
        and value.attr == "ids"
        or isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr in _PLAIN_DATA_METHODS
    )
    is_records = (
        not plain_data
        and node_is_orm(value, orm_vars, plain)
        and _clearly_records(value, orm_vars)
    )
    for target in node.targets:
        # `self = self.with_context(..)` still is the plain receiver.
        if isinstance(target, ast.Name) and target.id not in ("self", "cls"):
            if is_records:
                orm_vars.add(target.id)
                inferred.add(target.id)
            else:
                orm_vars.discard(target.id)
                inferred.discard(target.id)


def orm_calls_in_loops(
    tree: ast.AST, methods: set[str]
) -> Iterator[tuple[ast.Call, LoopNode, bool]]:
    """ORM calls of the given method names that run once per iteration of a loop.

    Loops are ``for``, ``while`` and comprehensions. Names bound to records (loop
    variables over records, locals assigned from an ORM expression) are followed
    within their block. The flag says the finding rests on that inference (the receiver
    is rooted at a local, or the loop is a comprehension) and not on a plain
    ``self`` / ``env[...]`` receiver in a ``for`` / ``while``.
    """

    reported: set[int] = set()  # calls an enclosing loop already yielded

    def walk(
        node: ast.AST,
        orm_vars: set[str],
        inferred: set[str],
        plain: frozenset[str] | set[str],
    ) -> Iterator[tuple[ast.Call, LoopNode, bool]]:
        orm_vars, inferred = set(orm_vars), set(inferred)
        if isinstance(node, ast.ClassDef):
            plain = plain_self_attrs(node)
        if isinstance(node, LoopNode):
            _bind_loop_targets(node, orm_vars, inferred, plain)
            if not is_bounded_loop(node):
                for n in per_iteration_nodes(node):
                    if (
                        isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in methods
                        and id(n) not in reported
                        and receiver_is_orm(n, orm_vars, plain)
                    ):
                        reported.add(id(n))
                        guessed = isinstance(
                            node, Comprehension
                        ) or not receiver_is_orm(n, orm_vars - inferred, plain)
                        yield n, node, guessed
        for child in ast.iter_child_nodes(node):
            yield from walk(child, orm_vars, inferred, plain)
            if isinstance(child, ast.Assign):
                _bind_assign(child, orm_vars, inferred, plain)

    yield from walk(tree, set(), set(), frozenset())


# The only calls a loop may make for one of its queries to count as unaffected by it.
# Anything else (create / write / unlink / flush / invalidate / message_post / action_* /
# a helper of the class ...) may change what the query sees, so the query stays medium.
_READ_ONLY_CALLS = {
    "search",
    "search_count",
    "search_read",
    "search_fetch",
    "read",
    "read_group",
    "_read_group",
    "browse",
    "exists",
    "ref",
    "mapped",
    "filtered",
    "filtered_domain",
    "sorted",
    "with_context",
    "with_company",
    "with_user",
    "with_env",
    "sudo",
    "get",
    "items",
    "keys",
    "values",
    "append",
    "format",
    "join",
    "split",
    "strip",
    "lower",
    "upper",
    "startswith",
    "endswith",
    "replace",
    # builtins and translation, called by name
    "len",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "sum",
    "min",
    "max",
    "any",
    "all",
    "range",
    "enumerate",
    "zip",
    "round",
    "abs",
    "isinstance",
    "getattr",
    "hasattr",
    "repr",
    "_",
}
_CONTAINER_MUTATORS = {
    "append",
    "extend",
    "update",
    "add",
    "pop",
    "setdefault",
    "remove",
    "insert",
    "clear",
    "discard",
    "sort",
}


# Calls a loop's `write` / `create` values may hold and still be the same on every pass:
# `fields.Datetime.now()` / `today()` (one value per request for practical purposes),
# builtins, translation and the context switches of the receiver chain.
_SAME_EACH_PASS_CALLS = {
    "now",
    "today",
    "_",
    "len",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "with_context",
    "with_company",
    "with_user",
    "sudo",
}


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _store_root(target: ast.AST) -> str | None:
    """Name at the root of an assignment target (``vals['a']`` -> ``vals``)."""
    while isinstance(target, (ast.Attribute, ast.Subscript, ast.Starred)):
        target = target.value
    return target.id if isinstance(target, ast.Name) else None


def _is_store(n: ast.AST) -> bool:
    """An attribute / item store or delete anywhere: an assignment target, also inside a
    tuple or list target, a ``for`` / ``with`` / comprehension target."""
    return isinstance(n, (ast.Attribute, ast.Subscript)) and isinstance(
        n.ctx, (ast.Store, ast.Del)
    )


def _bound_names(n: ast.AST) -> set[str]:
    """Names a statement binds other than through an ``ast.Name`` store: ``except .. as e``,
    match captures, ``import .. as v``, ``def`` / ``class`` names."""
    if isinstance(n, ast.ExceptHandler) and n.name:
        return {n.name}
    if isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
        return {n.name}
    if isinstance(n, ast.MatchMapping) and n.rest:
        return {n.rest}
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in n.names}
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {n.name}
    return set()


def _names_changed_by_loop(loop: ast.For | ast.While) -> set[str]:
    """Names the loop rebinds or mutates: its target, every name stored or bound in it, the
    root of ``x[k] = v`` / ``x.a = v`` and the receiver of ``x.append(...)``-like calls."""
    changed: set[str] = set()
    if isinstance(loop, ast.For):
        changed |= {n.id for n in ast.walk(loop.target) if isinstance(n, ast.Name)}
    for stmt in [*loop.body, *([loop.test] if isinstance(loop, ast.While) else [])]:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                changed.add(n.id)
            elif _is_store(n):
                changed.add(_store_root(n) or "")
            elif (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in _CONTAINER_MUTATORS
            ):
                changed.add(_store_root(n.func.value) or "")
            else:
                changed |= _bound_names(n)
    changed.discard("")
    return changed


_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
# Not "every iteration": a branch, a short circuit, a deferred or separate scope.
_NOT_EVERY_ITERATION = (
    ast.IfExp,
    ast.BoolOp,
    ast.Lambda,
    ast.If,
    ast.Try,
    ast.While,
    ast.For,
    ast.AsyncFor,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Match,
    ast.Assert,  # its message runs only on failure, all of it not at all under -O
    *_COMPREHENSIONS,
    *([ast.TryStar] if hasattr(ast, "TryStar") else []),
)


def _free_names(node: ast.AST, bound: frozenset[str] = frozenset()) -> set[str]:
    """Names *node* reads that it does not bind itself (comprehension variables and
    lambda arguments shadow only inside their own scope)."""
    if isinstance(node, ast.Name):
        return {node.id} - bound if isinstance(node.ctx, ast.Load) else set()
    if isinstance(node, _COMPREHENSIONS):
        names: set[str] = set()
        inner = set(bound)
        for i, gen in enumerate(node.generators):
            names |= _free_names(gen.iter, bound if i == 0 else frozenset(inner))
            inner |= {n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name)}
            for cond in gen.ifs:
                names |= _free_names(cond, frozenset(inner))
        elts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        for elt in elts:
            names |= _free_names(elt, frozenset(inner))
        return names
    if isinstance(node, ast.Lambda):
        args = {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg)}
        defaults = [*node.args.defaults, *(d for d in node.args.kw_defaults if d)]
        return _free_names(node.body, bound | args) | {
            n for d in defaults for n in _free_names(d, bound)
        }
    return {n for c in ast.iter_child_nodes(node) for n in _free_names(c, bound)}


def _runs_every_iteration(node: ast.AST, call: ast.Call) -> bool:
    """*call* sits in *node* on a path with no branch, short-circuit or deferred scope."""
    if node is call:
        return True
    if isinstance(node, _NOT_EVERY_ITERATION):
        return False
    children = (
        # `a < b < c`: `c` runs only when `a < b` holds
        [node.left, node.comparators[0]]
        if isinstance(node, ast.Compare)
        else ast.iter_child_nodes(node)
    )
    return any(_runs_every_iteration(c, call) for c in children)


def _leaves_early(loop: ast.For | ast.While) -> bool:
    """A ``break`` / ``continue`` / ``return`` / ``yield`` in the body: not every pass
    reaches the end (a generator may be closed at its ``yield``)."""
    return any(
        isinstance(n, (ast.Break, ast.Continue, ast.Return, ast.Yield, ast.YieldFrom))
        for stmt in loop.body
        for n in ast.walk(stmt)
    )


def _may_change_records(loop: ast.For | ast.While, call: ast.Call) -> bool:
    """The loop stores to an attribute / item (``rec.state = ..``, ``rec['a'] += 1``,
    ``a.x, b = ..``, ``for r.state in ..``, ``del rec.a``) or makes a call that is not a
    plain read. The *call* itself is not counted; its arguments are."""
    head = [loop.target] if isinstance(loop, ast.For) else []
    for stmt in [*head, *loop.body]:
        for n in ast.walk(stmt):
            if _is_store(n):
                return True
            if (
                isinstance(n, ast.Call)
                and n is not call
                and _call_name(n) not in _READ_ONLY_CALLS
            ):
                return True
    return False


def _receiver_names(receiver: ast.expr, keep_root: bool) -> set[str]:
    """Names a call's receiver depends on; the root of the chain (``rec`` in
    ``rec.with_context(a=x)``) only when *keep_root*."""
    root: ast.AST = receiver
    while isinstance(root, (ast.Attribute, ast.Subscript, ast.Call)):
        root = root.func if isinstance(root, ast.Call) else root.value
    return {
        n.id
        for n in ast.walk(receiver)
        if isinstance(n, ast.Name) and (keep_root or n is not root)
    }


def _only_statement(loop: ast.For, call: ast.Call) -> bool:
    """The loop body is the call's statement and nothing else (docstring / ``pass`` aside)."""
    body = [
        s
        for s in loop.body
        if not isinstance(s, ast.Pass)
        and not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    return len(body) == 1 and isinstance(body[0], ast.Expr) and body[0].value is call


def is_repeated_unchanged(call: ast.Call, loop: LoopNode, tree: ast.AST) -> bool:
    """The call does the same thing on every pass: nothing the loops around it change
    reaches it. It is the one loop shape that is plainly wrong and cheap to prove.

    * A query (``search`` ...) is a direct statement of the ``for`` body (no ``if`` /
      ``try`` / ``match`` / ``assert`` / nested function around it, not past a short
      circuit, no ``break`` / ``continue`` / ``return`` / ``yield`` in the body), its
      receiver and arguments use neither a loop variable nor a name the loops rebind,
      and the loop changes no record: no attribute / item store, no call other than a
      plain read (``_READ_ONLY_CALLS``). It can be hoisted out of the loop. In a nested
      loop the query is judged against the innermost loop that runs it; names the outer
      loops rebind count too.
    * A ``write`` / ``create`` is the only statement of the body, its arguments (and the
      context it is called with) do not use the loop and call nothing that may return
      another value on the next pass (only ``_SAME_EACH_PASS_CALLS``, such as
      ``fields.Datetime.now()``): ``for r in recs: r.write(vals)`` is
      ``recs.write(vals)``.

    Blind spot: a query is judged by the loop body alone. A helper the body calls is
    treated as a possible write (so the query stays medium), but nothing is known about
    what the helper does, and a write made by an earlier statement outside the loop, a
    cron or another transaction is not seen. Calls are allowed by name only, so a
    user-defined ``get`` / ``format`` that writes, or a name that aliases one the loop
    mutates (``d = domain; d.append(..)``), is not seen either. A ``write`` / ``create``
    is not checked for what the batched form would change (order of effects, per-record
    side effects of ``write`` overrides), only for being the lone statement.
    """
    if not isinstance(loop, ast.For) or not isinstance(call.func, ast.Attribute):
        return False
    method = call.func.attr
    writes = method in ("create", "write")
    if any(isinstance(n, ast.NamedExpr) for n in ast.walk(call)):
        return False  # a name bound inside the call leaks out of it
    if writes and not _only_statement(loop, call):
        return False
    if writes and any(
        isinstance(n, ast.Call) and _call_name(n) not in _SAME_EACH_PASS_CALLS
        for n in ast.walk(call)
        if n is not call
    ):
        return False  # `next_by_code()`, `uuid4()`, a helper ... differ on each pass
    if not any(_runs_every_iteration(stmt, call) for stmt in loop.body):
        return False
    if _leaves_early(loop) or (not writes and _may_change_records(loop, call)):
        return False
    changed: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.For, ast.While))
            and node.lineno <= call.lineno <= (node.end_lineno or node.lineno)
            and any(n is call for n in ast.walk(node))
        ):
            changed |= _names_changed_by_loop(node)
    used = _free_names(
        ast.Module(
            body=[ast.Expr(a) for a in [*call.args, *(k.value for k in call.keywords)]],
            type_ignores=[],
        )
    )
    used |= _receiver_names(call.func.value, keep_root=method != "write")
    return not used & changed


_MODEL_BASE_NAMES = {"Model", "TransientModel", "AbstractModel", "BaseModel"}


def is_model_class(cls: ast.ClassDef) -> bool:
    """True for a class that declares an Odoo model.

    It either derives from ``models.Model`` / ``TransientModel`` / ``AbstractModel`` /
    ``BaseModel`` or sets ``_name`` / ``_inherit`` itself. A plain Python mixin without
    either is not a model, even though models may inherit from it.
    """
    for base in cls.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name in _MODEL_BASE_NAMES:
            return True
    for stmt in cls.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else []
        if isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        if any(
            isinstance(t, ast.Name) and t.id in ("_name", "_inherit") for t in targets
        ):
            return True
    return False


def odoo_major(version: str) -> int | None:
    """Major number of an Odoo version string (``"19.0"`` -> 19), None if unparsable."""
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


_RECORD_ROOTS = {"self", "cls", "env", "request"}


def receiver_kind(node: ast.expr) -> str:
    """``record`` (self / env / request rooted), ``super`` or ``other`` for a call receiver."""
    while True:
        if isinstance(node, ast.Attribute):
            if node.attr == "env":
                return "record"
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "super":
                return "super"
            node = node.func
        else:
            break
    if isinstance(node, ast.Name) and node.id in _RECORD_ROOTS:
        return "record"
    return "other"


# pylint-odoo's own marker. A developer who writes it is explicitly asserting that the
# flagged pattern is intended, so rules covering the same check honour it like pylint.
_PYLINT_DISABLE_RE = re.compile(r"pylint:\s*disable\s*=\s*([\w\-,\s]+)")


def pylint_disabled_ranges(
    source: str, tree: ast.AST, names: Iterable[str]
) -> list[tuple[int, int]]:
    """Line ranges where ``# pylint: disable=<one of names>`` is in effect.

    A trailing comment covers its own line; a comment on its own line covers the
    rest of the enclosing function (or module), as in pylint.
    """
    wanted = set(names)
    ranges: list[tuple[int, int]] = []
    if "pylint" not in source:  # tokenizing every file only to find nothing is slow
        return ranges
    scopes = [
        (n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return ranges
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _PYLINT_DISABLE_RE.search(tok.string)
        if not match or not wanted & {
            name.strip() for name in match.group(1).split(",")
        }:
            continue
        line = tok.start[0]
        if tok.line[: tok.start[1]].strip():  # trailing comment
            ranges.append((line, line))
            continue
        enclosing = [end for start, end in scopes if start <= line <= end]
        ranges.append((line, min(enclosing) if enclosing else 10**9))
    return ranges
