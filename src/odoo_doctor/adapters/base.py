# src/odoo_doctor/adapters/base.py
"""BackendAdapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from odoo_doctor.core.diagnostics import Diagnostic


class BackendAdapter(Protocol):
    name: str

    def is_available(self) -> bool:
        """Check if the external tool is installed."""
        ...

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        """Run the tool and return normalized diagnostics."""
        ...
