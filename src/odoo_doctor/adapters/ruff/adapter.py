# src/odoo_doctor/adapters/ruff/adapter.py
"""Ruff adapter — runs ruff check and maps output to Diagnostic."""

from __future__ import annotations

import json
import os
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
from odoo_doctor.core.text import safe_text


@dataclass
class _RuleMapping:
    category: str
    tier: str
    confidence: str


_UNMAPPED = _RuleMapping(category="Uncategorized", tier="P3", confidence="low")


class RuffAdapter:
    name = "ruff"
    config_key = "ruff"

    def __init__(self) -> None:
        self._mapping = self._load_mapping()

    def is_available(self) -> bool:
        return shutil.which("ruff") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        if not self.is_available():
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "missing executable",
                    "Ruff executable was not found on PATH.",
                )
            ]

        module = Path(module_path).resolve()
        targets = lint_targets(module)
        if not targets:
            return []
        by_file = targets != [module]
        try:
            # The repo's own ruff.toml / pyproject.toml [tool.ruff] is honoured (the team's
            # rules), found by ruff from the linted paths, never from the cwd. Ruff cannot run
            # code from config, but `cache-dir` could make it write elsewhere, so: --no-cache
            # (also no .ruff_cache in the repo), a scratch cwd and HOME (no user-level config,
            # nothing written to the repo) and a secret-free environment. Residual risk: a
            # hostile config can disable or change ruff's own findings (not the native rules).
            with tempfile.TemporaryDirectory(prefix="odoo-doctor-ruff-") as scratch:
                result = subprocess.run(
                    [
                        "ruff",
                        "check",
                        "--no-cache",
                        # ruff's default excludes (node_modules ...) for files listed one by one
                        *(["--force-exclude"] if by_file else []),
                        "--output-format=json",
                        *map(str, targets),  # absolute: cwd is the scratch dir
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
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
                    "Ruff did not finish within 60 seconds.",
                )
            ]
        except FileNotFoundError:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "missing executable",
                    "Ruff executable was not found on PATH.",
                )
            ]

        try:
            raw = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "parse failure",
                    "Ruff returned invalid JSON output.",
                )
            ]

        if not isinstance(raw, list):
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "parse failure",
                    "Ruff JSON output did not match the expected list schema.",
                )
            ]

        diags = self._parse_output(
            raw, module_name=module_path.name, odoo_version=odoo_version
        )
        if result.returncode != 0 and not diags:
            return [
                _adapter_warning(
                    self.name,
                    module_path,
                    odoo_version,
                    "process error",
                    f"Ruff exited with status {result.returncode} but produced no findings; "
                    "the run may have failed (configuration or internal error"
                    f"{_cause(result.stderr)}).",
                )
            ]
        return diags

    def _parse_output(
        self, raw: list[dict], module_name: str, odoo_version: str
    ) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            code = item.get("code") or ""
            filename = item.get("filename") or ""
            if code == "F401" and filename.endswith("__init__.py"):
                continue

            mapping = self._mapping.get(code, _UNMAPPED)
            location = item.get("location") or {}

            diags.append(
                Diagnostic(
                    module=module_name,
                    file_path=filename,
                    line=location.get("row", 0) or 0,
                    column=location.get("column", 0) or 0,
                    rule=code,
                    category=mapping.category,
                    severity="warning" if mapping.tier in ("P2", "P3") else "error",
                    tier=mapping.tier,
                    source="ruff",
                    confidence=mapping.confidence,
                    title=f"Ruff {code}",
                    message=item.get("message") or "",
                    help=f"See Ruff docs for rule {code}.",
                    url=f"https://docs.astral.sh/ruff/rules/{code}",
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


def _cause(stderr: str) -> str:
    """Ruff's own complaint (last line: the root cause of a bad or `required-version` config)."""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    line = lines[-1].removeprefix("Cause: ") if lines else ""
    return f": {safe_text(line)[:200]}" if line else ""


_ENV_KEEP = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT")


def _safe_env(scratch: str) -> dict[str, str]:
    """Only what ruff needs to start: no tokens, no ``RUFF_*`` overrides."""
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update(HOME=scratch, TMPDIR=scratch, TEMP=scratch)
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
