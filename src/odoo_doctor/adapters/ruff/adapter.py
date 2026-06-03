# src/odoo_doctor/adapters/ruff/adapter.py
"""Ruff adapter — runs ruff check and maps output to Diagnostic."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from odoo_doctor.core.diagnostics import Diagnostic


@dataclass
class _RuleMapping:
    category: str
    tier: str
    confidence: str


_UNMAPPED = _RuleMapping(category="Uncategorized", tier="P3", confidence="low")


class RuffAdapter:
    name = "ruff"

    def __init__(self) -> None:
        self._mapping = self._load_mapping()

    def is_available(self) -> bool:
        return shutil.which("ruff") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                ["ruff", "check", "--output-format=json", str(module_path)],
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        try:
            raw = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            return []

        return self._parse_output(raw, module_name=module_path.name, odoo_version=odoo_version)

    def _parse_output(
        self, raw: list[dict], module_name: str, odoo_version: str
    ) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for item in raw:
            code = item.get("code", "")
            mapping = self._mapping.get(code, _UNMAPPED)

            diags.append(Diagnostic(
                module=module_name,
                file_path=item.get("filename", ""),
                line=item.get("location", {}).get("row", 0),
                column=item.get("location", {}).get("column", 0),
                rule=code,
                category=mapping.category,
                severity="warning" if mapping.tier in ("P2", "P3") else "error",
                tier=mapping.tier,
                source="ruff",
                confidence=mapping.confidence,
                title=f"Ruff {code}",
                message=item.get("message", ""),
                help=f"See Ruff docs for rule {code}.",
                url=f"https://docs.astral.sh/ruff/rules/{code}",
                odoo_version=odoo_version,
            ))
        return diags

    def _load_mapping(self) -> dict[str, _RuleMapping]:
        mapping_file = Path(__file__).parent / "rule_mapping.toml"
        if not mapping_file.exists():
            return {}
        with open(mapping_file, "rb") as f:
            raw = tomllib.load(f)
        result: dict[str, _RuleMapping] = {}
        for code, info in raw.get("rules", {}).items():
            result[code] = _RuleMapping(
                category=info["category"],
                tier=info["tier"],
                confidence=info.get("confidence", "high"),
            )
        return result
