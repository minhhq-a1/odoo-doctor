# src/odoo_doctor/adapters/pylint_odoo/adapter.py
"""Pylint-Odoo adapter — runs pylint with odoo plugin and maps output."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
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
from odoo_doctor.core.source import lint_targets

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
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "missing executable",
                    "Pylint executable was not found on PATH.",
                )
            ]

        targets = lint_targets(Path(module_path).resolve())
        if not targets:
            return []
        try:
            # Pylint executes the `init-hook` of any rc/pyproject it discovers from the
            # cwd, so the scanned repo must never be that source: pin an empty rcfile and
            # run from a scratch dir with a secret-free environment.
            with tempfile.TemporaryDirectory(prefix="odoo-doctor-pylint-") as scratch:
                rcfile = Path(scratch) / "pylintrc"
                rcfile.write_text("")
                result = subprocess.run(
                    [
                        "pylint",
                        f"--rcfile={rcfile}",
                        "--load-plugins=pylint_odoo",
                        "--output-format=text",
                        *map(str, targets),  # absolute: cwd is the scratch dir
                    ],
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    timeout=120,
                    check=False,
                    cwd=scratch,
                    env=_safe_env(scratch),
                )
        except subprocess.TimeoutExpired:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "timeout",
                    "Pylint-Odoo did not finish within 120 seconds.",
                )
            ]
        except FileNotFoundError:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "missing executable",
                    "Pylint executable was not found on PATH.",
                )
            ]

        if result.stderr and "No module named pylint_odoo" in result.stderr:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "missing plugin",
                    "Pylint-Odoo plugin is not installed or cannot be imported.",
                )
            ]

        diags = self._parse_output(
            result.stdout or "", module_name=module_path.name, odoo_version=odoo_version
        )
        if result.returncode != 0 and not diags:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "process error",
                    f"Pylint exited with status {result.returncode} but produced no findings; "
                    "the run may have failed (configuration or internal error).",
                )
            ]
        return diags

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

            diags.append(
                Diagnostic(
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
                )
            )
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


_ENV_KEEP = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT")


def _safe_env(scratch: str) -> dict[str, str]:
    """Only what pylint needs to start: no tokens, no PYTHONPATH/PYTHONSTARTUP."""
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update(HOME=scratch, PYLINTHOME=scratch, TMPDIR=scratch, TEMP=scratch)
    return env


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
