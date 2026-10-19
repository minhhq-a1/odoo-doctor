# src/odoo_doctor/core/cache.py
"""Project-level incremental scan cache.

The cache stores ONE scan result keyed by a fingerprint covering every input
that can change results: all scanned file contents, the resolved config, the
Odoo version, the active ruleset, the identity of every plugin rule (distribution
version and a hash of its source), the versions of the enabled linters (ruff,
pylint), the tool version, and CACHE_VERSION. The entry also stores what the live
scan computed that cannot be recomputed from the findings (the detected Odoo
version, suppression stats, line counts) so a hit reproduces the live result. Because
several rules are cross-module, caching is all-or-nothing: any change to any
input invalidates the whole cache. This trades incremental granularity for
provable correctness (no stale cross-module findings).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, packages_distributions
from importlib.metadata import version as _pkg_version
from pathlib import Path

from odoo_doctor.core.source import (
    is_scannable,
    path_within,
    read_bytes,
    warn_skipped,
)

# Bump when the serialized Diagnostic payload schema changes. A mismatch makes
# any older on-disk cache miss cleanly instead of raising on Diagnostic(**old).
# v2 adds suppression_stats, v3 adds python_lines, v4 adds the scan's detected version
# and puts plugin and linter identities in the key.
CACHE_VERSION = 4

_CACHE_FILE = "scan_cache.json"
_SCANNED_SUFFIXES = {".py", ".xml", ".csv"}


def _tool_version() -> str:
    try:
        return _pkg_version("odoo-doctor")
    except PackageNotFoundError:  # editable/source checkout without metadata
        return "0+unknown"


# config key -> executable the adapter runs
_ADAPTER_TOOLS = {"ruff": "ruff", "pylint_odoo": "pylint"}
_tool_versions: dict[str, str] = {}  # resolved executable path -> `--version` output


def _linter_version(exe: str) -> str:
    """``<exe> --version``, run once per process; a fixed marker when it cannot run."""
    path = shutil.which(exe)
    if path is None:
        return "unavailable"
    if path not in _tool_versions:
        try:
            with tempfile.TemporaryDirectory(prefix="odoo-doctor-version-") as scratch:
                env = {
                    k: os.environ[k]
                    for k in (
                        "PATH",
                        "LANG",
                        "LC_ALL",
                        "SYSTEMROOT",
                        "COMSPEC",
                        "PATHEXT",
                    )
                    if k in os.environ
                }
                env.update(HOME=scratch, TMPDIR=scratch, TEMP=scratch)
                out = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    cwd=scratch,  # pylint prints the rc file it found from the cwd
                    env=env,
                )
            _tool_versions[path] = (
                out.stdout.strip() if out.returncode == 0 else "error"
            )
        except (OSError, subprocess.SubprocessError):
            _tool_versions[path] = "error"
    return _tool_versions[path]


def adapter_identities(adapters: dict[str, bool]) -> tuple[str, ...]:
    """``adapter=<key>:<version>`` for every linter adapter that can run (off when disabled)."""
    return tuple(
        f"adapter={key}:" + (_linter_version(exe) if adapters.get(key, True) else "off")
        for key, exe in sorted(_ADAPTER_TOOLS.items())
    )


def _source_hash(module_name: str) -> str:
    # shortcut: hashes only the rule's own module file, not sibling helper modules;
    # the distribution version covers installed plugins, upgrade if that proves too weak.
    path = getattr(sys.modules.get(module_name), "__file__", None)
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]  # type: ignore[arg-type]
    except (OSError, TypeError):
        return "unavailable"


def plugin_identities(rules: Iterable[tuple[object, object]]) -> tuple[str, ...]:
    """Identity of every registered rule that is not built in: the distribution
    (name-version) that ships its module and a hash of the module's source file.

    ``name@min_version`` alone cannot see a plugin rule's code change."""
    owners: dict[str, list[str]] | None = None
    found: list[str] = []
    for meta, func in rules:
        mod = getattr(func, "__module__", None) or ""
        if mod == "odoo_doctor" or mod.startswith("odoo_doctor."):
            continue
        if owners is None:
            try:
                owners = packages_distributions()
            except Exception:  # noqa: BLE001 - metadata is best effort
                owners = {}
        dists = []
        for dist in owners.get(mod.split(".")[0], []):
            try:
                dists.append(f"{dist}-{_pkg_version(dist)}")
            except PackageNotFoundError:
                dists.append(dist)
        found.append(
            f"plugin={getattr(meta, 'name', '?')}:{mod}:{','.join(sorted(dists))}:"
            f"{_source_hash(mod)}"
        )
    return tuple(sorted(found))


def project_fingerprint(
    addon_paths: Iterable[Path],
    config_repr: str,
    version: str,
    ruleset: tuple[str, ...],
    extra: Iterable[str] = (),
) -> str:
    """Hash every input that can change scan results.

    - addon_paths: the resolved scan roots (their scanned files' contents).
    - config_repr: a stable string repr of the effective config.
    - version: the resolved Odoo version.
    - ruleset: a sorted tuple of active rule identities (name+min_version).
    - extra: further identities (plugin rules, linter versions) hashed as-is.
    """
    h = hashlib.sha256()
    h.update(f"cache_version={CACHE_VERSION}\0".encode())
    h.update(f"tool={_tool_version()}\0".encode())
    h.update(f"odoo={version}\0".encode())
    h.update(f"config={config_repr}\0".encode())
    for r in sorted(ruleset):
        h.update(f"rule={r}\0".encode())
    for e in sorted(extra):
        h.update(f"{e}\0".encode())

    # File contents across all roots, in a deterministic order.
    seen: set[str] = set()
    for root in addon_paths:
        root = Path(root)
        if not root.exists():
            continue
        files = sorted(
            p
            for p in root.rglob("*")
            if p.suffix in _SCANNED_SUFFIXES and is_scannable(p)
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
    """Single-entry cache: the fingerprint plus everything a hit must reproduce."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self._fp: str | None = None
        self._diagnostics: list | None = None
        self._suppression_stats: dict | None = None
        self._python_lines: dict | None = None
        self._version: str | None = None

    @property
    def _path(self) -> Path:
        return self.cache_dir / _CACHE_FILE

    def load(self) -> None:
        # the cache lives in the scanned repo: a FIFO, a huge file or a symlink out of
        # the repo there is not read
        raw = read_bytes(self._path, self.cache_dir.parent)
        if raw is None:
            return
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:  # includes UnicodeDecodeError
            return
        if not isinstance(data, dict):
            return
        if data.get("cache_version") != CACHE_VERSION:
            return  # schema changed -> ignore stale cache
        self._fp = data.get("fp")
        self._diagnostics = data.get("diagnostics")
        self._suppression_stats = data.get("suppression_stats")
        self._python_lines = data.get("python_lines")
        self._version = data.get("version")

    def save(self) -> None:
        if self._fp is None:
            return
        payload = json.dumps(
            {
                "cache_version": CACHE_VERSION,
                "fp": self._fp,
                "diagnostics": self._diagnostics or [],
                "suppression_stats": self._suppression_stats or {},
                "python_lines": self._python_lines or {},
                "version": self._version,
            }
        )
        # The cache lives in the scanned repo, which is untrusted: never write through a
        # symlinked directory or file out of it. A temp file in the directory plus
        # os.replace swaps the name itself, so a symlink at the target is replaced, not followed.
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if not path_within(self.cache_dir, self.cache_dir.parent):
                warn_skipped(
                    self.cache_dir, "cache directory leaves the scanned directory"
                )
                return
            fd, tmp = tempfile.mkstemp(dir=self.cache_dir, prefix=".scan_cache-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, self._path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError as exc:
            warn_skipped(self.cache_dir, f"cache not written ({exc.strerror or exc})")

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

    def lookup_version(self, fingerprint: str) -> str | None:
        """The Odoo version the stored scan ran as (None on a miss)."""
        if self._fp == fingerprint:
            return self._version
        return None

    def store(
        self,
        fingerprint: str,
        diagnostics: list,
        suppression_stats: dict | None = None,
        python_lines: dict | None = None,
        version: str | None = None,
    ) -> None:
        self._fp = fingerprint
        self._diagnostics = diagnostics
        self._suppression_stats = suppression_stats or {}
        self._python_lines = python_lines or {}
        self._version = version
