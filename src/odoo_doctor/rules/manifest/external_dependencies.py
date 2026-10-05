# src/odoo_doctor/rules/manifest/external_dependencies.py
"""Rule: missing-external-dependency [Module Hygiene, P2]."""

from __future__ import annotations

import ast
import sys
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._ast_helpers import is_test_file
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Standard-library modules removed in recent Pythons: this tool may run on a newer
# Python than the Odoo it analyses.
_REMOVED_STDLIB = frozenset(
    [
        "imp",
        "distutils",
        "asyncore",
        "asynchat",
        "smtpd",
        "telnetlib",
        "cgi",
        "cgitb",
        "crypt",
        "pipes",
        "nntplib",
        "imghdr",
        "sndhdr",
        "audioop",
        "aifc",
        "chunk",
        "mailcap",
        "msilib",
        "nis",
        "ossaudiodev",
        "spwd",
        "sunau",
        "uu",
        "xdrlib",
        "lib2to3",
    ]
)
_STDLIB = set(sys.stdlib_module_names) | _REMOVED_STDLIB | {"__future__"}

# Import names of the packages Odoo 17-19 installs from its own requirements.txt
# (plus their well-known transitive dependencies): addons may import them freely.
ODOO_CORE_IMPORTS = frozenset(
    {
        "asn1crypto", "babel", "cbor2", "certifi", "chardet", "charset_normalizer",
        "cryptography", "dateutil", "decorator", "docutils", "ebaysdk", "freezegun",
        "geoip2", "gevent", "greenlet", "idna", "jinja2", "ldap", "lxml",
        "lxml_html_clean", "magic", "markupsafe", "num2words", "ofxparse", "openpyxl",
        "openssl", "passlib", "pil", "pkg_resources", "polib", "psutil", "psycopg2",
        "pydot", "pypdf", "pypdf2", "pytz", "qrcode", "reportlab", "requests",
        "rjsmin", "sass", "sassutils", "serial", "setuptools", "six", "stdnum",
        "urllib3", "usb", "vobject", "werkzeug", "xlrd", "xlsxwriter", "xlwt", "zeep",
    }
)  # fmt: skip

_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in _IMPORT_ERRORS for n in names)


class _ImportCollector(ast.NodeVisitor):
    """Collects (top-level package, line) for imports that are not optional."""

    def __init__(self) -> None:
        self.imports: list[tuple[str, int]] = []
        self._guard = 0

    def visit_Try(self, node: ast.Try) -> None:
        guarded = any(_catches_import_error(h) for h in node.handlers)
        self._guard += guarded
        self.generic_visit(node)
        self._guard -= guarded

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        self.visit(test)
        self._guard += type_checking
        for stmt in node.body:
            self.visit(stmt)
        self._guard -= type_checking
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        if not self._guard:
            for alias in node.names:
                self.imports.append((alias.name.split(".")[0], node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not self._guard and node.level == 0 and node.module:
            self.imports.append((node.module.split(".")[0], node.lineno))


def _local_names(ctx: ModuleContext) -> set[str]:
    names = {ctx.name.lower()}
    for child in ctx.path.iterdir():
        names.add(child.stem.lower() if child.is_file() else child.name.lower())
    return names


@rule(
    name="missing-external-dependency",
    category="Module Hygiene",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_external_dependency(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag third-party imports not covered by `external_dependencies['python']`."""
    # Packages declared by this addon or by anything it depends on are covered. If
    # the dependency chain reaches a module we have no manifest for, that module
    # might declare the package, so the finding is only medium confidence.
    closure, complete = ctx.resolver.dependency_closure(ctx.depends)
    declared = set(ctx.resolver.module_external_python(ctx.name) or set())
    declared |= {
        d.split(".")[0].strip().lower()
        for d in (ctx.manifest.raw.get("external_dependencies") or {}).get("python", [])
        if isinstance(d, str)
    }
    for module in closure:
        declared |= ctx.resolver.module_external_python(module) or set()
    confidence = "high" if complete else "medium"

    local = _local_names(ctx)
    first_site: dict[str, tuple[str, int]] = {}
    count: dict[str, int] = {}

    for py_file in sorted(ctx.path.rglob("*.py")):
        rel = py_file.relative_to(ctx.path)
        if is_test_file(py_file, ctx.name) or "migrations" in rel.parts:
            continue
        if py_file.name == "__manifest__.py":
            continue
        tree = parse_python(py_file)
        if tree is None:
            continue
        collector = _ImportCollector()
        collector.visit(tree)
        for top, line in collector.imports:
            key = top.lower()
            if (
                top in _STDLIB
                or key in {"odoo", "openerp"}
                or key in ODOO_CORE_IMPORTS
                or key in declared
                or key in local
                or ctx.resolver.is_known_module(top)
            ):
                continue
            count[top] = count.get(top, 0) + 1
            first_site.setdefault(top, (str(py_file), line))

    diags: list[Diagnostic] = []
    for top in sorted(first_site):
        path, line = first_site[top]
        places = count[top]
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=path,
                line=line,
                column=0,
                rule="missing-external-dependency",
                category="Module Hygiene",
                severity="warning",
                tier="P2",
                source="native",
                confidence=confidence,
                title=f"Python package '{top}' is not declared in external_dependencies",
                message=(
                    f"'{top}' is imported in {places} place(s) (first here) but "
                    f"'{ctx.name}' does not list it under "
                    "external_dependencies['python'], so installing the module "
                    "without it fails at import time instead of with a clear error."
                ),
                help=(
                    f'Add "external_dependencies": {{"python": ["{top}"]}} to '
                    "__manifest__.py, or guard the import with try/except ImportError "
                    "if the package is optional."
                ),
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
