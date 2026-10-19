# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python, read_source
from odoo_doctor.rules._ast_helpers import is_test_file, pylint_disabled_ranges
from odoo_doctor.rules._taint import Taint, TaintVisitor, trusting_opaque_values
from odoo_doctor.rules.registry import rule

_CR_METHODS = {"execute", "executemany"}
# `cr`, `env.cr`, `self._cr`, `request.env.cr`, `request.cr`: anything ending in a cursor name.
_CR_NAMES = {"cr", "_cr"}
# DDL and other statements that do not contain SELECT/UPDATE/INSERT/DELETE/CREATE anyway.
_STATEMENT_START = re.compile(
    r"\s*(WITH|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COPY|VACUUM|REINDEX|ANALYZE|EXPLAIN"
    r"|LOCK|SET|CALL|MERGE)\b",
    re.IGNORECASE,
)


def _is_upgrade_script(file_path: Path) -> bool:
    """`migrations/` (up to Odoo 17) and `upgrades/` (Odoo 18+) hold one-off scripts."""
    return bool({"migrations", "upgrades"} & set(Path(file_path).parts))


@rule(
    name="raw-sql-string-interpolation",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_raw_sql_interpolation(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Find cr.execute() calls with dynamically interpolated SQL strings."""
    # Tests and migration/upgrade scripts run on a developer's or admin's database, never on
    # request data, so dynamic SQL there is not an injection vector.
    if is_test_file(file_path, module_name) or _is_upgrade_script(file_path):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    disabled = pylint_disabled_ranges(
        read_source(file_path) or "", tree, ("sql-injection",)
    ) + _input_free_hook_ranges(tree)
    owners = _owners(tree)
    methods = _method_ids(tree)
    visitor = _RawSqlVisitor(disabled, methods, owners)
    visitor.visit(tree)
    if not visitor.calls:
        return []
    # Second pass: trust every value that is not an entry point's parameter. A call that
    # is still dynamic then is built from something a caller outside the module controls.
    # A private helper's parameter is untrusted once a caller hands it such a value; the
    # pass repeats so the input can travel a few hops (bounded: this is a heuristic).
    untrusted: dict[_Key, set[str]] = {}
    for _ in range(_MAX_HOPS + 1):
        with trusting_opaque_values():
            caller = _RawSqlVisitor(disabled, methods, owners, untrusted, True)
            caller.visit(tree)
        if all(
            names <= untrusted.get(key, set()) for key, names in caller.marks.items()
        ):
            break
        for key, names in caller.marks.items():
            untrusted.setdefault(key, set()).update(names)
    reached = {(c.lineno, c.col_offset) for c in caller.calls}
    return [
        _make_diagnostic(
            call,
            file_path,
            module_name,
            odoo_version,
            "high" if (call.lineno, call.col_offset) in reached else "medium",
        )
        for call in visitor.calls
    ]


# ORM hooks that run at install/upgrade time (SQL views are created in `init`).
_INSTALL_HOOKS = {"init", "_auto_init"}


def _input_free_hook_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges of install-time hooks that take nothing but ``self``.

    With no parameter, no caller-supplied data reaches the SQL they build, only class
    metadata such as ``self._table`` and ``self._query()``.
    """
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            takes_only_self = (
                len(args.args) + len(args.posonlyargs) == 1
                and not args.kwonlyargs
                and args.vararg is None
                and args.kwarg is None
            )
            if node.name in _INSTALL_HOOKS and takes_only_self:
                ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


_MAX_HOPS = 3
_Def = ast.FunctionDef | ast.AsyncFunctionDef
# (class name, or "" for a module-level function; function name)
_Key = tuple[str, str]


def _owners(tree: ast.Module) -> dict[_Key, _Def]:
    """Methods by (class, name) and module-level functions by ("", name)."""
    found: dict[_Key, _Def] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            body, owner = node.body, node.name
        elif node is tree:
            body, owner = tree.body, ""
        else:
            continue
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[(owner, stmt.name)] = stmt
    return found


def _method_ids(tree: ast.AST) -> set[int]:
    """`id()` of every function defined directly in a class body."""
    return {
        id(stmt)
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef)
        for stmt in cls.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _decorator_name(node: ast.expr) -> str:
    return _dotted_name(node.func if isinstance(node, ast.Call) else node).rsplit(
        ".", 1
    )[-1]


class _RawSqlVisitor(TaintVisitor):
    def __init__(
        self,
        disabled_ranges: list[tuple[int, int]],
        method_ids: set[int],
        owners: dict[_Key, _Def],
        untrusted: dict[_Key, set[str]] | None = None,
        caller_params: bool = False,
    ) -> None:
        super().__init__()
        self._disabled_ranges = disabled_ranges
        self._method_ids = method_ids
        self._owners = owners
        self._key_of = {id(f): k for k, f in owners.items()}
        self._untrusted = untrusted or {}
        self._caller_params = caller_params
        self._classes: list[str] = []
        self.calls: list[ast.Call] = []
        # parameters of a private helper that a call handed a caller-controlled value
        self.marks: dict[_Key, set[str]] = {}
        # shortcut: cursor names are file-wide, not scoped; a reused name only widens matching.
        self._cursors: set[str] = set()

    def _note_cursor(self, target: ast.expr | None, value: ast.expr) -> None:
        if isinstance(target, ast.Name) and _opens_cursor(value):
            self._cursors.add(target.id)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._note_cursor(target, node.value)
        super().visit_Assign(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self._note_cursor(item.optional_vars, item.context_expr)
        super().visit_With(node)

    def param_taint(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef, name: str
    ) -> Taint:
        """Under ``trusting_opaque_values`` only an entry point's parameters stay opaque."""
        if not self._caller_params:
            return Taint.UNKNOWN
        if name in {"self", "cls"}:
            return Taint.SAFE
        key = self._key_of.get(id(func))
        handed = key is not None and name in self._untrusted.get(key, ())
        return Taint.UNKNOWN if handed or self._is_entry_point(func) else Taint.SAFE

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._classes.append(node.name)
        super().visit_ClassDef(node)
        self._classes.pop()

    def _callee(self, node: ast.Call) -> tuple[_Key, int] | None:
        """The function a `self._m(...)`, `cls._m(...)` or `helper(...)` call reaches."""
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in {"self", "cls"}:
                return ((self._classes[-1] if self._classes else "", func.attr), 1)
            return None
        return (("", func.id), 0) if isinstance(func, ast.Name) else None

    def _note_call(self, node: ast.Call) -> None:
        callee = self._callee(node)
        target = self._owners.get(callee[0]) if callee else None
        if callee is None or target is None:
            return
        key, skip = callee
        args = target.args
        names = [a.arg for a in (*args.posonlyargs, *args.args)][skip:]
        handed: set[str] = set()
        for i, arg in enumerate(node.args):
            if self.taint(arg) == Taint.SAFE:
                continue
            if isinstance(arg, ast.Starred):
                handed.update(names[i:])
            elif i < len(names):
                handed.add(names[i])
            elif args.vararg is not None:
                handed.add(args.vararg.arg)
        for kw in node.keywords:
            if self.taint(kw.value) == Taint.SAFE:
                continue
            if kw.arg is None:
                handed.update(names)
                if args.kwarg is not None:
                    handed.add(args.kwarg.arg)
            elif kw.arg in names or kw.arg in {a.arg for a in args.kwonlyargs}:
                handed.add(kw.arg)
            elif args.kwarg is not None:
                handed.add(args.kwarg.arg)
        if handed:
            self.marks.setdefault(key, set()).update(handed)

    def _is_entry_point(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Callable from outside the module: a route, or a public method (RPC reaches those)."""
        if any(_decorator_name(d) == "route" for d in func.decorator_list):
            return True
        return id(func) in self._method_ids and not func.name.startswith("_")

    def check_call(self, node: ast.Call) -> None:
        if self._caller_params:
            self._note_call(node)
        if not (_is_cursor_execute(node, self._cursors) and node.args):
            return
        sql_arg = node.args[0]
        if _is_plain_text_format(sql_arg):
            return
        if self.taint(sql_arg) != Taint.UNSAFE:
            return
        if any(start <= node.lineno <= end for start, end in self._disabled_ranges):
            return
        self.calls.append(node)


def _opens_cursor(node: ast.expr) -> bool:
    """`registry.cursor()`, `self.pool.cursor()`, `closing(registry.cursor())`."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cursor":
            return True
        return any(_opens_cursor(a) for a in node.args)
    return False


def _is_cursor_execute(node: ast.Call, cursors: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _CR_METHODS:
        return False
    receiver = node.func.value
    if _opens_cursor(receiver):
        return True
    name = _dotted_name(receiver)
    return name.rsplit(".", 1)[-1] in _CR_NAMES or name in cursors


def _is_plain_text_format(node: ast.expr) -> bool:
    """`"some {} text".format(x)` with no SQL keyword is not a query being built."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    receiver = node.func.value
    return (
        node.func.attr == "format"
        and isinstance(receiver, ast.Constant)
        and isinstance(receiver.value, str)
        and not any(
            token in receiver.value.upper()
            for token in ("SELECT", "UPDATE", "INSERT", "DELETE", "CREATE")
        )
        and not _STATEMENT_START.match(receiver.value)
    )


def _dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _make_diagnostic(
    node: ast.Call,
    file_path: Path,
    module_name: str,
    odoo_version: str,
    confidence: str,
) -> Diagnostic:
    method = node.func.attr if isinstance(node.func, ast.Attribute) else "execute"
    if confidence == "high":
        message = (
            f"'{method}()' at line {node.lineno} uses dynamic SQL string construction "
            "from a parameter a caller controls. Vulnerable to SQL injection."
        )
    else:
        message = (
            f"'{method}()' at line {node.lineno} builds its SQL by string interpolation "
            "from model metadata, ORM-built fragments or a private helper's parameter "
            "(the pattern Odoo's own addons use). Check that no interpolated value "
            "can come from a user."
        )
    return Diagnostic(
        module=module_name,
        file_path=str(file_path),
        line=node.lineno,
        column=node.col_offset,
        rule="raw-sql-string-interpolation",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence=confidence,
        title="SQL injection via string interpolation",
        message=message,
        help="Use parameterized queries: cr.execute('SELECT ... WHERE name = %s', (param,)).",
        odoo_version=odoo_version,
    )
