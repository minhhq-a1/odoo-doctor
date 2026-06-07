# src/odoo_doctor/adapters/pylint_odoo/adapter.py
"""Pylint-Odoo adapter — runs pylint with odoo plugin and maps output."""

from __future__ import annotations

import re
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

_LINE_RE = re.compile(
    r"^(.+?):(\d+):(\d+):\s+([A-Z]\d+):\s+(.+?)(?:\s+\(([^)]+)\))?\s*$"
)


@dataclass
class _RuleMapping:
    category: str
    tier: str
    confidence: str


_UNMAPPED = _RuleMapping(category="Uncategorized", tier="P3", confidence="low")


class PylintOdooAdapter:
    name = "pylint-odoo"
    config_key = "pylint_odoo"

    def __init__(self) -> None:
        self._mapping = self._load_mapping()

    def is_available(self) -> bool:
        return shutil.which("pylint") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        if not self.is_available():
            return [_adapter_warning(
                self.name, module_path, odoo_version, "missing executable",
                "Pylint executable was not found on PATH.",
            )]

        try:
            result = subprocess.run(
                [
                    "pylint",
                    "--load-plugins=pylint_odoo",
                    "--output-format=text",
                    str(module_path),
                ],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return [_adapter_warning(
                self.name, module_path, odoo_version, "timeout",
                "Pylint-Odoo did not finish within 120 seconds.",
            )]
        except FileNotFoundError:
            return [_adapter_warning(
                self.name, module_path, odoo_version, "missing executable",
                "Pylint executable was not found on PATH.",
            )]

        if result.stderr and "No module named pylint_odoo" in result.stderr:
            return [_adapter_warning(
                self.name, module_path, odoo_version, "missing plugin",
                "Pylint-Odoo plugin is not installed or cannot be imported.",
            )]

        return self._parse_output(
            result.stdout or "", module_name=module_path.name, odoo_version=odoo_version
        )

    def _parse_output(
        self, raw_text: str, module_name: str, odoo_version: str
    ) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        for line in raw_text.strip().splitlines():
            match = _LINE_RE.match(line.strip())
            if not match:
                continue

            file_path, line_no, col, code, message, _symbol = match.groups()
            mapping = self._mapping.get(code, _UNMAPPED)

            diags.append(Diagnostic(
                module=module_name,
                file_path=file_path,
                line=int(line_no),
                column=int(col),
                rule=code,
                category=mapping.category,
                severity="warning" if mapping.tier in ("P2", "P3") else "error",
                tier=mapping.tier,
                source="pylint-odoo",
                confidence=mapping.confidence,
                title=f"Pylint-Odoo {code}",
                message=message.strip(),
                help=f"See Pylint-Odoo docs for {code}.",
                url="https://github.com/OCA/pylint-odoo",
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


def _adapter_warning(
    tool: str,
    module_path: Path,
    odoo_version: str,
    reason: str,
    detail: str,
) -> Diagnostic:
    return Diagnostic(
        module=module_path.name,
        file_path=str(module_path),
        line=1,
        column=0,
        rule=f"adapter-{tool}-warning",
        category="Maintainability",
        severity="warning",
        tier="P3",
        source=tool,
        confidence="low",
        title=f"{tool} adapter warning: {reason}",
        message=detail,
        help=f"Install or configure {tool}, or disable the adapter in odoo-doctor.toml.",
        odoo_version=odoo_version,
    )
