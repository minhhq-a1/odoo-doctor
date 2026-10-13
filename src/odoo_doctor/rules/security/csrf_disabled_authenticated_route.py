# src/odoo_doctor/rules/security/csrf_disabled_authenticated_route.py
"""Rule: csrf-disabled-authenticated-route [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_migration_file, is_test_file
from odoo_doctor.rules.registry import rule

# Odoo only checks the token for these (http.py: SAFE_HTTP_METHODS / CSRF_FREE_METHODS).
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _route_call(decorator: ast.expr) -> ast.Call | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return decorator if name == "route" else None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _literal_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _methods(node: ast.expr | None) -> set[str] | None:
    """The route's literal HTTP methods, None when absent (all) or not a literal."""
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values = {_literal_str(elt) for elt in node.elts}
    return {v.upper() for v in values if v}


@rule(
    name="csrf-disabled-authenticated-route",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_csrf_disabled_authenticated_route(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag state-changing ``type='http'`` routes that authenticate by session but skip CSRF.

    A browser sends the session cookie on a cross-site request, so such a route can be
    triggered by any web page the logged-in user visits. ``auth='public'`` / ``'none'``
    webhooks, which carry no session identity of their own, and JSON routes (which the
    CSRF check never covers) are not reported.
    """
    if is_test_file(file_path, module_name) or is_migration_file(
        file_path, module_name
    ):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []

    diags: list[Diagnostic] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in func.decorator_list:
            call = _route_call(decorator)
            if call is None:
                continue
            csrf = _keyword(call, "csrf")
            if not (isinstance(csrf, ast.Constant) and csrf.value is False):
                continue
            auth = _keyword(call, "auth")
            auth_value = "user" if auth is None else _literal_str(auth)
            route_type = _keyword(call, "type")
            type_value = "http" if route_type is None else _literal_str(route_type)
            if auth_value != "user" or type_value != "http":
                continue
            methods_node = _keyword(call, "methods")
            methods = _methods(methods_node)
            if methods_node is not None and methods is None:
                continue  # computed methods: cannot tell
            if methods is not None and not methods - _SAFE_METHODS:
                continue  # GET / HEAD only: Odoo never checks the token there
            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=str(file_path),
                    line=decorator.lineno,
                    column=decorator.col_offset,
                    rule="csrf-disabled-authenticated-route",
                    category="Security",
                    severity="warning",
                    tier="P1",
                    source="native",
                    confidence="high" if methods is not None else "medium",
                    title="Logged-in route has CSRF protection disabled",
                    message=(
                        f"`{func.name}` runs as the logged-in user (auth='user') but is "
                        "declared with csrf=False. A page on any other site can make the "
                        "visitor's browser submit a request to it, and the session cookie "
                        "authenticates it."
                        + (
                            ""
                            if methods is not None
                            else " The route does not restrict `methods`, so it accepts POST."
                        )
                    ),
                    help=(
                        "Remove csrf=False and send the token (`request.csrf_token()`) "
                        "with the form or request. If a trusted third party calls this "
                        "route, move it to auth='public' and verify a signature or secret "
                        "instead of relying on the session."
                    ),
                    odoo_version=odoo_version,
                )
            )
    return diags
