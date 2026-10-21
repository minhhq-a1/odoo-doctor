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
import os
from collections.abc import Iterable, Iterator
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

# Bump when the serialized Diagnostic payload schema changes. A mismatch makes
# any older on-disk cache miss cleanly instead of raising on Diagnostic(**old).
CACHE_VERSION = 4  # v4 retains each module's effective Odoo version

_CACHE_FILE = "scan_cache.json"
_SCANNED_SUFFIXES = {".py", ".pyi", ".xml", ".csv", ".toml", ".ipynb"}
# Not scan inputs, and rewritten by tooling between scans (a running Odoo, pytest,
# Finder, an editor): hashing them would turn every such write into a cache miss.
_SKIP_DIRS = {".git", ".ruff_cache", ".mypy_cache", ".pytest_cache", "__pycache__"}
_SKIP_FILES = {".DS_Store", "Thumbs.db"}
_SKIP_SUFFIXES = {".pyc", ".pyo", ".swp", ".swo"}


def _tool_version() -> str:
    try:
        return _pkg_version("odoo-doctor")
    except PackageNotFoundError:  # editable/source checkout without metadata
        return "0+unknown"


def _walk_files(root: Path, excluded: set[str]) -> Iterator[tuple[str, str | None]]:
    """Yield (absolute path, symlink target or None) for every input file under *root*.

    One `scandir` pass: directories are resolved (to honour *excluded*), files are not,
    which keeps the cache-hit path cheap on trees with tens of thousands of files.
    """
    pending = [str(root.absolute())]
    while pending:
        folder = pending.pop()
        if excluded and os.path.realpath(folder) in excluded:
            continue
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in _SKIP_DIRS:
                            pending.append(entry.path)
                    elif (
                        entry.name not in _SKIP_FILES
                        and os.path.splitext(entry.name)[1] not in _SKIP_SUFFIXES
                        and entry.is_file()
                    ):
                        link = entry.is_symlink()
                        yield (
                            entry.path,
                            (os.path.realpath(entry.path) if link else None),
                        )
        except OSError:
            continue


def project_fingerprint(
    addon_paths: Iterable[Path],
    config_repr: str,
    version: str,
    ruleset: tuple[str, ...],
    extra_files: Iterable[Path] = (),
    extra_identities: tuple[str, ...] = (),
    excluded_paths: Iterable[Path] = (),
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
    for identity in extra_identities:
        h.update(f"dependency={identity}\0".encode())

    # File contents across all roots, in a deterministic order. Value: the symlink
    # target (None for regular files), so retargeting an alias changes the hash.
    extras = {str(Path(p).resolve()) for p in extra_files}
    files: dict[str, str | None] = dict.fromkeys(extras)
    excluded = {str(Path(p).resolve()) for p in excluded_paths}
    for root in addon_paths:
        files.update(_walk_files(Path(root), excluded))
    for path in sorted(files):
        h.update(f"{path}\0{files[path] or path}\0".encode("utf-8", "surrogateescape"))
        # Every file's existence matters to manifest asset checks. Only inputs
        # consumed as source/config need their contents hashed as well.
        if path not in extras and os.path.splitext(path)[1] not in _SCANNED_SUFFIXES:
            continue
        try:
            h.update(Path(path).read_bytes())
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
        self._suppression_stats: dict | None = None
        self._python_lines: dict | None = None
        self._module_versions: dict | None = None

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
        self._suppression_stats = data.get("suppression_stats")
        self._python_lines = data.get("python_lines")
        self._module_versions = data.get("module_versions")

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
                    "suppression_stats": self._suppression_stats or {},
                    "python_lines": self._python_lines or {},
                    "module_versions": self._module_versions or {},
                }
            ),
            encoding="utf-8",
        )

    def lookup(self, fingerprint: str) -> list | None:
        if self._fp == fingerprint:
            return self._diagnostics
        return None

    def lookup_stats(self, fingerprint: str) -> dict:
        """Suppression stats stored with the entry for *fingerprint* ({} on a miss)."""
        if self._fp == fingerprint:
            return self._suppression_stats or {}
        return {}

    def lookup_lines(self, fingerprint: str) -> dict:
        """Per-module Python line counts stored with the entry ({} on a miss)."""
        if self._fp == fingerprint:
            return self._python_lines or {}
        return {}

    def store(
        self,
        fingerprint: str,
        diagnostics: list,
        suppression_stats: dict | None = None,
        python_lines: dict | None = None,
        module_versions: dict[str, str] | None = None,
    ) -> None:
        self._fp = fingerprint
        self._diagnostics = diagnostics
        self._suppression_stats = suppression_stats or {}
        self._python_lines = python_lines or {}
        self._module_versions = module_versions or {}

    def lookup_versions(self, fingerprint: str) -> dict[str, str]:
        if self._fp == fingerprint:
            return self._module_versions or {}
        return {}
