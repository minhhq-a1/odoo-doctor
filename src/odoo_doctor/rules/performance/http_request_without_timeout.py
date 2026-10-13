# src/odoo_doctor/rules/performance/http_request_without_timeout.py
"""Rule: http-request-without-timeout [Performance, P2]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_migration_file, is_test_file
from odoo_doctor.rules.registry import rule

_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}


class _Names:
    """What the module's imports and assignments make an HTTP call out of."""

    def __init__(self, tree: ast.AST) -> None:
        self.requests_modules: set[str] = set()  # `import requests [as r]`
        self.request_funcs: dict[str, str] = {}  # `from requests import get [as g]`
        self.urlopen_funcs: set[str] = set()  # `from urllib.request import urlopen`
        self.urllib_request_modules: set[str] = set()  # `import urllib.request as ur`
        self.session_funcs: set[str] = set()  # `from requests import Session [as S]`
        self.sessions: set[str] = set()  # names bound to `requests.Session()`
        self._collect(tree)

    def _collect(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "requests":
                        self.requests_modules.add(alias.asname or "requests")
                    elif alias.name == "urllib.request":
                        self.urllib_request_modules.add(alias.asname or "urllib")
            elif isinstance(node, ast.ImportFrom) and not node.level:
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if node.module == "requests" and alias.name in _VERBS:
                        self.request_funcs[bound] = alias.name
                    elif node.module == "requests" and alias.name == "Session":
                        self.session_funcs.add(bound)
                    elif node.module == "urllib.request" and alias.name == "urlopen":
                        self.urlopen_funcs.add(bound)
                    elif node.module == "urllib" and alias.name == "request":
                        self.urllib_request_modules.add(bound)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and self._is_session_ctor(node.value):
                for target in node.targets:
                    key = _binding_key(target)
                    if key:
                        self.sessions.add(key)
            elif isinstance(node, ast.With):
                for item in node.items:
                    key = _binding_key(item.optional_vars)
                    if key and self._is_session_ctor(item.context_expr):
                        self.sessions.add(key)

    def _is_session_ctor(self, node: ast.expr | None) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "Session":
            return (
                isinstance(func.value, ast.Name)
                and func.value.id in self.requests_modules
            )
        return isinstance(func, ast.Name) and func.id in self.session_funcs

    def describe(self, call: ast.Call) -> str | None:
        """``requests.get`` style label when the call is an HTTP call, else None."""
        func = call.func
        if isinstance(func, ast.Name):
            if func.id in self.request_funcs:
                return f"requests.{self.request_funcs[func.id]}()"
            if func.id in self.urlopen_funcs:
                return "urlopen()"
            return None
        if not isinstance(func, ast.Attribute):
            return None
        root = func.value
        if isinstance(root, ast.Name):
            if root.id in self.requests_modules and func.attr in _VERBS:
                return f"requests.{func.attr}()"
            if root.id in self.sessions and func.attr in _VERBS:
                return f"session.{func.attr}()"
        key = _binding_key(root)
        if key and key in self.sessions and func.attr in _VERBS:
            return f"session.{func.attr}()"
        if func.attr == "urlopen" and (
            isinstance(root, ast.Attribute)
            and root.attr == "request"
            and isinstance(root.value, ast.Name)
            and root.value.id in self.urllib_request_modules
            or isinstance(root, ast.Name)
            and root.id in self.urllib_request_modules
        ):
            return "urlopen()"
        return None


def _binding_key(node: ast.expr | None) -> str | None:
    """``name`` for a plain name, ``self.name`` for an attribute of ``self``."""
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return f"self.{node.attr}"
    return None


def _has_timeout(call: ast.Call, label: str) -> bool:
    if any(kw.arg == "timeout" or kw.arg is None for kw in call.keywords):
        return True  # a `**options` may carry it
    if label == "urlopen()":
        return len(call.args) >= 3 or any(isinstance(a, ast.Starred) for a in call.args)
    return any(isinstance(a, ast.Starred) for a in call.args)


@rule(
    name="http-request-without-timeout",
    category="Performance",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_http_request_without_timeout(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag ``requests`` / ``urlopen`` calls that never time out."""
    if is_test_file(file_path, module_name) or is_migration_file(
        file_path, module_name
    ):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []
    names = _Names(tree)
    diags: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        label = names.describe(node)
        if label is None or _has_timeout(node, label):
            continue
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="http-request-without-timeout",
                category="Performance",
                severity="warning",
                tier="P2",
                source="native",
                confidence="high",
                title=f"{label} has no timeout",
                message=(
                    f"{label} is called without `timeout`. Neither requests nor urlopen "
                    "gives up on its own, so one unresponsive server blocks the Odoo "
                    "worker until the server-wide limit kills it, together with every "
                    "request that worker was serving."
                ),
                help="Pass an explicit `timeout=` (seconds, or a (connect, read) pair).",
                odoo_version=odoo_version,
            )
        )
    return diags
