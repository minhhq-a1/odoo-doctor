# src/odoo_doctor/core/cache.py
"""Project-level incremental scan cache.

The cache stores ONE scan result keyed by a fingerprint covering every input
that can change results: all scanned file contents, the resolved config, the
Odoo version, the active ruleset, the tool version, and CACHE_VERSION. Because
several rules are cross-module, caching is all-or-nothing: any change to any
input invalidates the whole cache. This trades incremental granularity for
provable correctness (no stale cross-module findings).
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path
from typing import Iterable

# Bump when the serialized Diagnostic payload schema changes. A mismatch makes
# any older on-disk cache miss cleanly instead of raising on Diagnostic(**old).
CACHE_VERSION = 1

_CACHE_FILE = "scan_cache.json"
_SCANNED_SUFFIXES = {".py", ".xml", ".csv"}


def _tool_version() -> str:
    try:
        return _pkg_version("odoo-doctor")
    except PackageNotFoundError:  # editable/source checkout without metadata
        return "0+unknown"


def project_fingerprint(
    addon_paths: Iterable[Path],
    config_repr: str,
    version: str,
    ruleset: tuple[str, ...],
) -> str:
    """Hash every input that can change scan results.

    - addon_paths: the resolved scan roots (their scanned files' contents).
    - config_repr: a stable string repr of the effective config.
    - version: the resolved Odoo version.
    - ruleset: a sorted tuple of active rule identities (name+min_version).
    """
    h = hashlib.sha256()
    h.update(f"cache_version={CACHE_VERSION}\0".encode())
    h.update(f"tool={_tool_version()}\0".encode())
    h.update(f"odoo={version}\0".encode())
    h.update(f"config={config_repr}\0".encode())
    for r in sorted(ruleset):
        h.update(f"rule={r}\0".encode())

    # File contents across all roots, in a deterministic order.
    seen: set[str] = set()
    for root in addon_paths:
        root = Path(root)
        if not root.exists():
            continue
        files = sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and p.suffix in _SCANNED_SUFFIXES
        )
        for p in files:
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            h.update(key.encode("utf-8"))
            h.update(b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
            h.update(b"\0")
    return h.hexdigest()


class ScanCache:
    """Single-entry cache: {"cache_version": int, "fp": str, "diagnostics": list}."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self._fp: str | None = None
        self._diagnostics: list | None = None

    @property
    def _path(self) -> Path:
        return self.cache_dir / _CACHE_FILE

    def load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.get("cache_version") != CACHE_VERSION:
            return  # schema changed -> ignore stale cache
        self._fp = data.get("fp")
        self._diagnostics = data.get("diagnostics")

    def save(self) -> None:
        if self._fp is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "cache_version": CACHE_VERSION,
                    "fp": self._fp,
                    "diagnostics": self._diagnostics or [],
                }
            ),
            encoding="utf-8",
        )

    def lookup(self, fingerprint: str) -> list | None:
        if self._fp == fingerprint:
            return self._diagnostics
        return None

    def store(self, fingerprint: str, diagnostics: list) -> None:
        self._fp = fingerprint
        self._diagnostics = diagnostics
