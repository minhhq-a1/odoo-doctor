# src/odoo_doctor/rules/manifest/vendored_python_code.py
"""Rule: vendored-python-code [Maintainability, P3]."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Directory names that conventionally hold copied third-party code.
_VENDOR_DIRS = {
    "vendor", "vendored", "third_party", "thirdparty", "site-packages",
    "extern", "external", "lib", "libs",
}  # fmt: skip
# Well-known PyPI packages that should be declared, not copied into an addon.
_KNOWN_PACKAGES = {
    "attr", "barcode", "boto3", "botocore", "bs4", "certifi", "chardet", "click",
    "cryptography", "dateutil", "docx", "flask", "idna", "jinja2", "jwt", "lxml",
    "markupsafe", "numpy", "openpyxl", "pandas", "paramiko", "pil", "psycopg2",
    "pymysql", "pytz", "qrcode", "requests", "simplejson", "six", "suds",
    "urllib3", "werkzeug", "xlrd", "xlsxwriter", "xlwt", "yaml", "zeep",
}  # fmt: skip
# Never descended into: assets (JS libraries under static/lib are normal in Odoo),
# translations, tooling directories, and test code.
_SKIP_DIRS = {"static", "i18n", "node_modules", "tests", "migrations", "__pycache__"}


def _has_python(directory: Path) -> bool:
    return any(directory.rglob("*.py"))


def _vendored_roots(addon: Path) -> list[Path]:
    roots: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(addon):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        if current == addon:
            for d in list(dirnames):
                if (
                    d.lower() in _KNOWN_PACKAGES
                    and (current / d / "__init__.py").exists()
                ):
                    roots.append(current / d)
                    dirnames.remove(d)
            continue
        if current.name.endswith((".dist-info", ".egg-info")):
            roots.append(current)
            dirnames[:] = []
        elif current.name.lower() in _VENDOR_DIRS and _has_python(current):
            roots.append(current)
            dirnames[:] = []
    return roots


@rule(
    name="vendored-python-code",
    category="Maintainability",
    tier="P3",
    severity="info",
    default_confidence="medium",
    needs_context=True,
    min_version="14.0",
)
def check_vendored_python_code(ctx: ModuleContext) -> list[Diagnostic]:
    """Flag third-party Python code copied into the addon instead of declared."""
    manifest_file = str(ctx.path / "__manifest__.py")
    diags: list[Diagnostic] = []
    for root in _vendored_roots(ctx.path):
        rel = root.relative_to(ctx.path).as_posix()
        diags.append(
            Diagnostic(
                module=ctx.name,
                file_path=manifest_file,
                line=1,
                column=0,
                rule="vendored-python-code",
                category="Maintainability",
                severity="info",
                tier="P3",
                source="native",
                confidence="medium",
                title=f"Possible vendored third-party code in '{rel}'",
                message=(
                    f"'{rel}/' looks like third-party Python code copied into "
                    f"'{ctx.name}'. Vendored code is not updated with security "
                    "fixes and can clash with the version installed elsewhere."
                ),
                help=(
                    "Declare the package in external_dependencies['python'] and "
                    "install it with pip instead of copying it."
                ),
                odoo_version=ctx.odoo_version,
            )
        )
    return diags
