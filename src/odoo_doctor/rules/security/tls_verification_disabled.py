# src/odoo_doctor/rules/security/tls_verification_disabled.py
"""Rule: tls-verification-disabled [Security, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_migration_file, is_test_file
from odoo_doctor.rules.registry import rule

# A module that imports one of these talks to the network, so `verify=False` there is
# about a certificate. In any other file the keyword may belong to an unrelated function.
_NETWORK_MODULES = {
    "requests",
    "httpx",
    "urllib",
    "urllib3",
    "http",
    "aiohttp",
    "ssl",
    "zeep",
    "suds",
    "socket",
    "smtplib",
    "ftplib",
    "imaplib",
    "poplib",
    "xmlrpc",
    "websocket",
    "websockets",
    "paramiko",
}


def _imports_network_library(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots = {node.module.split(".")[0]}
        else:
            continue
        if roots & _NETWORK_MODULES:
            return True
    return False


def _is_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _attr_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


@rule(
    name="tls-verification-disabled",
    category="Security",
    tier="P1",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_tls_verification_disabled(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Flag code that switches off TLS certificate or hostname verification."""
    if is_test_file(file_path, module_name) or is_migration_file(
        file_path, module_name
    ):
        return []
    tree = parse_python(file_path)
    if tree is None:
        return []
    networked = _imports_network_library(tree)
    diags: list[Diagnostic] = []

    def emit(node: ast.AST, what: str, confidence: str) -> None:
        diags.append(
            Diagnostic(
                module=module_name,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="tls-verification-disabled",
                category="Security",
                severity="warning",
                tier="P1",
                source="native",
                confidence=confidence,
                title="TLS certificate verification is disabled",
                message=(
                    f"{what} turns off certificate verification, so anyone on the network "
                    "path can impersonate the server and read or alter the traffic, "
                    "including credentials and API tokens."
                ),
                help=(
                    "Remove it. For a server with a private or self-signed certificate, "
                    "point `verify` at its CA bundle (verify='/path/to/ca.pem') or install "
                    "the CA on the host."
                ),
                odoo_version=odoo_version,
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if any(kw.arg == "verify" and _is_false(kw.value) for kw in node.keywords):
                emit(
                    node,
                    "`verify=False`",
                    "high" if networked else "medium",
                )
            elif _attr_name(node.func) == "_create_unverified_context":
                emit(node, "`ssl._create_unverified_context()`", "high")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Attribute):
                    continue
                if target.attr in ("verify", "check_hostname") and _is_false(
                    node.value
                ):
                    emit(
                        node,
                        f"`{target.attr} = False`",
                        "high" if networked else "medium",
                    )
                elif target.attr == "verify_mode" and (
                    _attr_name(node.value) == "CERT_NONE"
                ):
                    emit(node, "`verify_mode = ssl.CERT_NONE`", "high")
                elif (
                    target.attr == "_create_default_https_context"
                    and _attr_name(node.value) == "_create_unverified_context"
                ):
                    emit(node, "`_create_default_https_context`", "high")
    return diags
