# src/odoo_doctor/core/pipeline.py
"""Seven-stage diagnostic pipeline — pure transformations."""

from __future__ import annotations

import fnmatch
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import CATEGORIES, Diagnostic

if TYPE_CHECKING:
    from odoo_doctor.core.config import OdooDoctorConfig
    from odoo_doctor.rules.registry import RuleMeta


# Type aliases
Suppressions = set[tuple[str, int, str]]  # (file_path, line, rule)
ActiveRules = dict[str, str | None]       # rule_name -> min_version or None


# --- Helpers ---

_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
_SOURCE_RANK = {"native": 2, "pylint-odoo": 1, "ruff": 1, "oca": 1}


def _version_gte(detected: str, minimum: str) -> bool:
    """Return True if detected >= minimum using first segment (e.g. '17.0' >= '14.0')."""
    try:
        det = float(detected.split(".")[0])
        mn = float(minimum.split(".")[0])
        return det >= mn
    except (ValueError, IndexError):
        return False


def derive_capabilities(detected_version: str, configured: list[str]) -> set[str]:
    """Derive full capability set from configured list and detected version."""
    caps = set(configured)
    if detected_version and detected_version != "unknown":
        caps.add(f"odoo:{detected_version.split('.')[0]}")
    return caps


def rule_is_enabled(meta: RuleMeta, detected_version: str, capabilities: set[str]) -> bool:
    """Return True if the rule is enabled based on version and capabilities."""
    if meta.min_version and not _version_gte(detected_version, meta.min_version):
        return False
    if not meta.requires_capabilities <= capabilities:
        return False
    if meta.excludes_capabilities & capabilities:
        return False
    return True


# --- Stage 1: Normalize ---

def normalize_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Normalize paths before downstream matching and deduplication."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        normalized_path = Path(d.file_path.replace("\\", "/")).resolve().as_posix()
        result.append(replace(d, file_path=normalized_path))
    return result


# --- Stage 2: Deduplicate ---

def deduplicate(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Group by (module, file_path, line, category, rule). Keep highest confidence,
    then prefer native source, then longest message.
    Two diagnostics with different rules are always distinct."""
    groups: dict[tuple[str, str, int, str, str], list[Diagnostic]] = {}
    for d in diagnostics:
        # Include rule in key so different rules at same location are kept
        key = (d.module, d.file_path, d.line, d.category, d.rule)
        groups.setdefault(key, []).append(d)

    result: list[Diagnostic] = []
    for group in groups.values():
        best = max(
            group,
            key=lambda d: (
                _CONFIDENCE_RANK.get(d.confidence, 0),
                _SOURCE_RANK.get(d.source, 0),
                len(d.message),
            ),
        )
        result.append(best)
    return result


# --- Stage 3: Severity overrides ---

def apply_severity_overrides(
    diagnostics: list[Diagnostic], config: OdooDoctorConfig
) -> list[Diagnostic]:
    """Change severity per config. severity='off' removes the diagnostic."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        override = config.severity_overrides.get(d.rule)
        if override is None:
            result.append(d)
        elif override == "off":
            continue
        else:
            result.append(replace(d, severity=override))
    return result


# --- Stage 4: Ignore filters ---

def apply_ignore_filters(
    diagnostics: list[Diagnostic], config: OdooDoctorConfig, base_path: Path | None = None
) -> list[Diagnostic]:
    """Remove diagnostics matching ignore rules, files, or modules."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        if d.rule in config.ignore_rules:
            continue
        if d.module in config.ignore_modules:
            continue
        if _matches_any_glob(d.file_path, config.ignore_files, base_path=base_path):
            continue
        result.append(d)
    return result


def _matches_any_glob(file_path: str, patterns: list[str], base_path: Path | None = None) -> bool:
    """Check if file_path matches any glob pattern, supporting ** via pathlib."""
    norm = file_path.replace("\\", "/")
    p = Path(norm)

    rel_path_str = None
    if p.is_absolute():
        bases = []
        if base_path is not None:
            bases.append(Path(base_path).resolve())
        bases.append(Path.cwd().resolve())
        for base in bases:
            try:
                rel_path_str = p.relative_to(base).as_posix()
                break
            except ValueError:
                pass

    paths_to_check = [norm]
    if rel_path_str:
        paths_to_check.append(rel_path_str)

    for pat in patterns:
        for path_str in paths_to_check:
            curr_p = Path(path_str)
            # Try fnmatch directly
            if fnmatch.fnmatch(path_str, pat):
                return True
            # Try pathlib.match (supports **)
            try:
                if curr_p.match(pat):
                    return True
            except ValueError:
                pass
            # Handle ** by checking if any sub-path matches
            # e.g. "**/migrations/**" should match "migrations/17.0/pre.py"
            if "**" in pat:
                # Strip leading **/ and check if the path contains the pattern
                pat_stripped = pat.strip("/").replace("**/", "").replace("/**", "")
                if pat_stripped and pat_stripped in path_str:
                    return True
                # Also try: split the pattern and check each segment
                parts = path_str.split("/")
                for i in range(len(parts)):
                    sub = "/".join(parts[i:])
                    if fnmatch.fnmatch(sub, pat.lstrip("*/")):
                        return True
    return False


# --- Stage 5: Inline suppressions ---

def apply_inline_suppressions(
    diagnostics: list[Diagnostic], suppressions: Suppressions
) -> list[Diagnostic]:
    """Remove diagnostics covered by inline suppression comments.

    Line 0 is a sentinel for file-wide suppressions: (file, 0, rule) suppresses
    that rule on every line of the file.
    """
    normalized_suppressions = {
        (Path(file_path.replace("\\", "/")).resolve().as_posix(), line, rule)
        for file_path, line, rule in suppressions
    }
    # Pre-compute file-wide suppressions: {(file, rule)} for line==0 entries
    file_wide = {
        (fp, rule) for fp, line, rule in normalized_suppressions if line == 0
    }
    return [
        d for d in diagnostics
        if (d.file_path, d.line, d.rule) not in normalized_suppressions
        and (d.file_path, d.rule) not in file_wide
    ]


# --- Stage 6: Version gates ---

def apply_version_gates(
    diagnostics: list[Diagnostic],
    active_rules: ActiveRules,
    detected_version: str,
) -> list[Diagnostic]:
    """Remove diagnostics whose rule requires a newer Odoo version."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        min_ver = active_rules.get(d.rule)
        if min_ver is None:
            result.append(d)
        elif _version_gte(detected_version, min_ver):
            result.append(d)
    return result


def apply_capability_gates(
    diagnostics: list[Diagnostic],
    config: OdooDoctorConfig,
    detected_version: str,
) -> list[Diagnostic]:
    """Remove diagnostics whose rules are gated out by capabilities/versions."""
    from odoo_doctor.rules.registry import default_registry
    derived_caps = derive_capabilities(detected_version, config.capabilities)
    result: list[Diagnostic] = []
    for d in diagnostics:
        meta_func = default_registry.get(d.rule)
        if meta_func is not None:
            meta, _ = meta_func
            if not rule_is_enabled(meta, detected_version, derived_caps):
                continue
        result.append(d)
    return result


# --- Stage 7: Score eligibility ---

def mark_score_eligibility(
    diagnostics: list[Diagnostic],
) -> list[bool]:
    """Return parallel list of booleans — True if the diagnostic counts toward score."""
    return [
        d.confidence == "high" and d.category in CATEGORIES
        for d in diagnostics
    ]


# --- Composed pipeline ---

def run_pipeline(
    diagnostics: list[Diagnostic],
    config: OdooDoctorConfig,
    suppressions: Suppressions,
    active_rules: ActiveRules,
    detected_version: str,
    base_path: Path | str | None = None,
) -> tuple[list[Diagnostic], list[bool]]:
    """Run all 7 pipeline stages in order. Returns (diagnostics, eligibility)."""
    if base_path is not None:
        base_path = Path(base_path).resolve()
    diags = normalize_diagnostics(diagnostics)
    diags = deduplicate(diags)
    diags = apply_severity_overrides(diags, config)
    diags = apply_ignore_filters(diags, config, base_path=base_path)
    diags = apply_inline_suppressions(diags, suppressions)
    diags = apply_version_gates(diags, active_rules, detected_version)
    diags = apply_capability_gates(diags, config, detected_version)
    eligible = mark_score_eligibility(diags)
    return diags, eligible
