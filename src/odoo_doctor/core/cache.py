# src/odoo_doctor/core/cache.py
"""Project-level incremental scan cache.

The cache stores ONE scan result keyed by a fingerprint covering every input
that can change results: all scanned file contents, the resolved config, the
Odoo version, the active ruleset, the identity of every plugin rule (distribution
version and a hash of its source), the versions of the enabled linters (ruff,
pylint), the tool version, and CACHE_VERSION. The entry also stores what the live
scan computed that cannot be recomputed from the findings (each module's Odoo
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
from collections.abc import Iterable, Iterator
from importlib.metadata import PackageNotFoundError, packages_distributions
from importlib.metadata import version as _pkg_version
from pathlib import Path

from odoo_doctor.core.source import (
    MAX_FILE_BYTES,
    SKIP_DIRS,
    path_within,
    read_bytes,
    warn_skipped,
)

# Bump when the serialized Diagnostic payload schema changes. A mismatch makes
# any older on-disk cache miss cleanly instead of raising on Diagnostic(**old).
# v2 adds suppression_stats, v3 adds python_lines, v4 retains each module's effective Odoo
# version, v5 puts plugin and linter identities in the key (and is the first version
# written by a build that has both the v4 per-module versions and these identities, so a
# v4 file from either lineage is rebuilt). v6 hashes .js files, which rules now read.
CACHE_VERSION = 6

_CACHE_FILE = "scan_cache.json"

_SCANNED_SUFFIXES = {".py", ".pyi", ".xml", ".csv", ".toml", ".ipynb", ".js"}
# Not scan inputs, and rewritten by tooling between scans (a running Odoo, pytest,
# Finder, an editor): hashing them would turn every such write into a cache miss.
_SKIP_DIRS = SKIP_DIRS  # the directories the scan walkers skip too
_SKIP_FILES = {".DS_Store", "Thumbs.db"}
_SKIP_SUFFIXES = {".pyc", ".pyo", ".swp", ".swo"}


def _tool_version() -> str:
    try:
        return _pkg_version("odoo-doctor")
    except PackageNotFoundError:  # editable/source checkout without metadata
        return "0+unknown"


# config key -> executable the adapter runs
_ADAPTER_TOOLS = {"ruff": "ruff", "pylint_odoo": "pylint"}
_tool_versions: dict[str, str] = {}  # resolved executable path -> `--version` output


def _safe_env(scratch: str) -> dict[str, str]:
    env = {
        k: os.environ[k]
        for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT")
        if k in os.environ
    }
    env.update(HOME=scratch, TMPDIR=scratch, TEMP=scratch)
    return env


def _pylint_odoo_version(pylint_path: str, scratch: str) -> str:
    """The pylint-odoo distribution version, read by the interpreter behind ``pylint``.

    ``pylint --version`` does not name its plugins, so upgrading pylint-odoo alone would keep
    stale findings on a hit. The interpreter is the shebang of the ``pylint`` script (or the
    ``python`` beside a launcher script); ``unknown`` when there is none (Windows launcher)
    or the import fails.
    """
    try:
        with open(pylint_path, "rb") as fh:
            first = fh.readline(512)
        if not first.startswith(b"#!"):
            return "unknown"
        interpreter = os.fsdecode(first[2:]).split()[0]
        if os.path.basename(interpreter) in ("sh", "bash", "env"):
            # a launcher script (uv's long-path form): the venv's own python sits beside it
            interpreter = str(Path(pylint_path).parent / "python")
        out = subprocess.run(
            [
                interpreter,
                "-c",
                "import importlib.metadata as m; print(m.version('pylint-odoo'))",
            ],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=30,
            check=False,
            cwd=scratch,
            env=_safe_env(scratch),
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, IndexError, subprocess.SubprocessError):
        return "unknown"


def _linter_version(exe: str) -> str:
    """``<exe> --version`` (plus pylint-odoo's version for pylint), run once per process;
    a fixed marker when it cannot run."""
    path = shutil.which(exe)
    if path is None:
        return "unavailable"
    if path not in _tool_versions:
        try:
            with tempfile.TemporaryDirectory(prefix="odoo-doctor-version-") as scratch:
                out = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    timeout=30,
                    check=False,
                    cwd=scratch,  # pylint prints the rc file it found from the cwd
                    env=_safe_env(scratch),
                )
                version = out.stdout.strip() if out.returncode == 0 else "error"
                if exe == "pylint" and out.returncode == 0:
                    version += f"|pylint-odoo={_pylint_odoo_version(path, scratch)}"
            _tool_versions[path] = version
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
    extra: Iterable[str] = (),
    extra_identities: tuple[str, ...] = (),
    excluded_paths: Iterable[Path] = (),
) -> str:
    """Hash every input that can change scan results.

    - addon_paths: the resolved scan roots (their scanned files' contents).
    - config_repr: a stable string repr of the effective config.
    - version: the resolved Odoo version.
    - ruleset: a sorted tuple of active rule identities (name+min_version).
    - extra: further identities (plugin rules, linter versions) hashed as-is.
    - extra_identities: inputs outside the addons (linter executables); excluded_paths:
      directories to skip (the cache's own).
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
    for identity in extra_identities:
        h.update(f"dependency={identity}\0".encode())

    # File contents across all roots, in a deterministic order. Value: the symlink
    # target (None for regular files), so retargeting an alias changes the hash.
    files: dict[str, str | None] = {}
    excluded = {str(Path(p).resolve()) for p in excluded_paths}
    for root in addon_paths:
        files.update(_walk_files(Path(root), excluded))
    for path in sorted(files):
        h.update(f"{path}\0{files[path] or path}\0".encode("utf-8", "surrogateescape"))
        # Every file's existence matters to manifest asset checks. Only inputs
        # consumed as source/config need their contents hashed as well.
        if os.path.splitext(path)[1] not in _SCANNED_SUFFIXES:
            continue
        # same guard as the scan: never open a special file, nor read one past the cap
        data = read_bytes(path)
        h.update(b"<unreadable>" if data is None else data)
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
        self._module_versions: dict | None = None

    @property
    def _path(self) -> Path:
        return self.cache_dir / _CACHE_FILE

    def load(self) -> None:
        # the cache lives in the scanned repo: a FIFO, a huge file or a symlink out of
        # the repo there is not read
        try:
            too_big = self._path.stat().st_size > MAX_FILE_BYTES
        except OSError:
            too_big = False
        if too_big:  # said here, so the reason is not the generic "larger than" skip
            warn_skipped(
                self._path,
                f"larger than {MAX_FILE_BYTES // 2**20} MiB: the cache is ignored and will be rewritten",
            )
            return
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
        self._module_versions = data.get("module_versions")

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
                "module_versions": self._module_versions or {},
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
        """Odoo version each module was scanned as ({} on a miss)."""
        if self._fp == fingerprint:
            return self._module_versions or {}
        return {}
