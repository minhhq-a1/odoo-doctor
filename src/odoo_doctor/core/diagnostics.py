# src/odoo_doctor/core/diagnostics.py
"""Diagnostic dataclass — the shared contract for every finding."""

from __future__ import annotations

from dataclasses import dataclass


CATEGORIES: list[str] = [
    "Security",
    "Correctness",
    "Performance",
    "Data Integrity",
    "Upgrade Safety",
    "Module Hygiene",
    "Maintainability",
]

TIER_IMPACT: dict[str, int] = {
    "P0": 25,
    "P1": 10,
    "P2": 4,
    "P3": 1,
}


@dataclass(frozen=True)
class Diagnostic:
    """A single finding from any source (native rule or external adapter)."""

    module: str
    file_path: str
    line: int
    column: int

    rule: str
    category: str
    severity: str       # "error" | "warning" | "info"
    tier: str           # "P0" | "P1" | "P2" | "P3"
    source: str         # "native" | "pylint-odoo" | "ruff" | "oca"
    confidence: str     # "high" | "medium" | "low"

    title: str
    message: str
    help: str
    odoo_version: str
    url: str | None = None
