# src/odoo_doctor/discovery/odoo_version.py
"""Conservative Odoo version detection."""

from __future__ import annotations

import importlib.metadata
import re

_ODOO_VERSION_RE = re.compile(r"^(1[4-9]|[2-9]\d)\.0")


def detect_odoo_version(
    cli_version: str | None = None,
    config_version: str | None = None,
    manifest_version: str | None = None,
) -> str:
    """Detect Odoo version using priority: CLI > config > manifest > package > unknown."""
    if cli_version:
        return cli_version

    if config_version:
        return config_version

    if manifest_version:
        m = _ODOO_VERSION_RE.match(manifest_version)
        if m:
            return f"{m.group(1)}.0"

    pkg_version = _detect_from_package()
    if pkg_version:
        return pkg_version

    return "unknown"


def _detect_from_package() -> str | None:
    """Try to detect Odoo version from the installed odoo Python package."""
    try:
        ver = importlib.metadata.version("odoo")
    except importlib.metadata.PackageNotFoundError:
        return None
    m = _ODOO_VERSION_RE.match(ver)
    if m:
        return f"{m.group(1)}.0"
    return None
