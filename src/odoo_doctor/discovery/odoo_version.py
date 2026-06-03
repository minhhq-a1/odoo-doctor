# src/odoo_doctor/discovery/odoo_version.py
"""Conservative Odoo version detection."""

from __future__ import annotations

import re

_ODOO_VERSION_RE = re.compile(r"^(1[4-9]|[2-9]\d)\.0")


def detect_odoo_version(
    cli_version: str | None = None,
    config_version: str | None = None,
    manifest_version: str | None = None,
) -> str:
    """Detect Odoo version using priority: CLI > config > manifest > unknown."""
    if cli_version:
        return cli_version

    if config_version:
        return config_version

    if manifest_version:
        m = _ODOO_VERSION_RE.match(manifest_version)
        if m:
            return f"{m.group(1)}.0"

    return "unknown"
